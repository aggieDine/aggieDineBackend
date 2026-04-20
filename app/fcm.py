"""
Firebase Cloud Messaging helper for silent data updates to frontend.
Sends JSON payloads via FCM without displaying notifications.
"""

import os
import json
import firebase_admin
from firebase_admin import credentials, messaging

# ==============================================================================
# FIREBASE INITIALIZATION (Runs once when Lambda imports this module)
# ==============================================================================
if not firebase_admin._apps:
    try:
        firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")
        if firebase_creds_json:
            cert_dict = json.loads(firebase_creds_json)
            cred = credentials.Certificate(cert_dict)
            firebase_admin.initialize_app(cred)
            print("[FCM] Firebase initialized successfully.")
        else:
            print("[Warning] FIREBASE_CREDENTIALS environment variable not found.")
    except Exception as e:
        print(f"[FCM Error] Failed to initialize Firebase: {e}")


# ==============================================================================
# DYNAMODB TOKEN MANAGEMENT
# ==============================================================================
def get_fcm_tokens_for_users(table, user_ids: list[str]) -> list[str]:
    """Fetch FCM device tokens for the given user IDs from DynamoDB."""
    from boto3.dynamodb.conditions import Key
    
    tokens = []
    for user_id in user_ids:
        try:
            response = table.query(
                KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("DEVICE#")
            )
            for item in response.get("Items", []):
                token = item["SK"].replace("DEVICE#", "")
                tokens.append(token)
        except Exception as e:
            print(f"[FCM] Error fetching tokens for user {user_id}: {e}")
    
    return tokens


def register_device_token(table, user_id: str, device_token: str):
    """Register a user's FCM device token."""
    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"DEVICE#{device_token}",
            "user_id": user_id,
            "device_token": device_token,
            "registered_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
    )
    print(f"[FCM] Registered device token for user {user_id}")


def unregister_device_token(table, user_id: str, device_token: str):
    """Remove a user's FCM device token."""
    table.delete_item(
        Key={
            "PK": f"USER#{user_id}",
            "SK": f"DEVICE#{device_token}",
        }
    )
    print(f"[FCM] Unregistered device token for user {user_id}")


# ==============================================================================
# MODERN HTTP v1 MESSAGE SENDING
# ==============================================================================
def send_data_message(
    table,
    user_ids: list[str],
    action: str,  # "event_created", "event_updated", "event_deleted"
    event_data: dict,
):
    """Send silent FCM data message to users' devices using the modern HTTP v1 API."""
    
    # Safety check: ensure Firebase actually initialized before trying to send
    if not firebase_admin._apps:
        print("[Warning] Firebase app not initialized - skipping data message")
        return

    if not user_ids:
        print("[FCM] No users to notify")
        return
    
    tokens = get_fcm_tokens_for_users(table, user_ids)
    
    if not tokens:
        print(f"[FCM] No FCM tokens found for users: {user_ids}")
        return
    
    # Convert datetime objects to ISO strings
    serializable_event = {
        **event_data,
        "time": event_data["time"].isoformat() if hasattr(event_data["time"], "isoformat") else event_data["time"],
        "created_at": event_data["created_at"].isoformat() if hasattr(event_data["created_at"], "isoformat") else event_data["created_at"],
        "updated_at": event_data["updated_at"].isoformat() if hasattr(event_data["updated_at"], "isoformat") else event_data["updated_at"],
    }
    
    # Construct the MulticastMessage
    message = messaging.MulticastMessage(
        data={
            "action": str(action),
            "event": json.dumps(serializable_event),
        },
        tokens=tokens,
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(content_available=True)
            )
        ),
        android=messaging.AndroidConfig(
            priority="high"
        )
    )
    
    try:
        response = messaging.send_each_for_multicast(message)
        print(f"[FCM] Data message sent: {response.success_count} succeeded, {response.failure_count} failed")
        
        # Log failures
        if response.failure_count > 0:
            for idx, res in enumerate(response.responses):
                if not res.success:
                    print(f"[FCM] Token failed ({tokens[idx]}): {res.exception}")
    except Exception as e:
        print(f"[FCM Error] Failed to send data message: {e}")


# ==============================================================================
# EVENT HELPERS
# ==============================================================================
def notify_event_created(table, event: dict):
    user_ids = [event["created_by"]] + event.get("invited_users", [])
    user_ids = list(set(user_ids))
    send_data_message(table, user_ids, "event_created", event)


def notify_event_updated(table, event: dict, previous_event: dict):
    current_users = [event["created_by"]] + event.get("invited_users", [])
    previous_users = [previous_event["created_by"]] + previous_event.get("invited_users", [])
    all_users = list(set(current_users + previous_users))
    send_data_message(table, all_users, "event_updated", event)


def notify_event_deleted(table, event: dict):
    user_ids = [event["created_by"]] + event.get("invited_users", [])
    user_ids = list(set(user_ids))
    send_data_message(table, user_ids, "event_deleted", event)
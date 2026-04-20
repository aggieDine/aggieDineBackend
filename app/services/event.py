import uuid
from datetime import datetime, timezone, timedelta

from boto3.dynamodb.conditions import Key, Attr

from app.schemas.event import EventCreate, EventUpdate


# DynamoDB key structure:
# PK: EVENT#YYYY-MM-DD  (date of the event for easy date-based queries)
# SK: TIME#{ISO time}#ID#{uuid}  (sorts chronologically within a day)


def _make_pk(event_time: datetime) -> str:
    date_str = event_time.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return f"EVENT#{date_str}"


def _make_sk(event_time: datetime, event_id: str) -> str:
    time_str = event_time.astimezone(timezone.utc).isoformat()
    return f"TIME#{time_str}#ID#{event_id}"


def _format_event(item: dict) -> dict:
    return {
        "event_id":      item["event_id"],
        "location":      item["location"],
        "time":          item["time"],
        "is_private":    item["is_private"],
        "invited_users": item.get("invited_users", []),
        "created_by":    item["created_by"],
        "created_at":    item["created_at"],
        "updated_at":    item["updated_at"],
        "message":       item["message"]
    }


def create_event(table, data: EventCreate, user_id: str) -> dict:
    event_id = str(uuid.uuid4())
    now      = datetime.now(timezone.utc).isoformat()
    time_iso = data.time.astimezone(timezone.utc).isoformat()

    item = {
        "PK":           _make_pk(data.time),
        "SK":           _make_sk(data.time, event_id),
        "event_id":     event_id,
        "location":     data.location,
        "time":         time_iso,
        "is_private":   data.is_private,
        "invited_users": data.invited_users,
        "created_by":   user_id,
        "created_at":   now,
        "updated_at":   now,
        "message":      data.message
    }
    table.put_item(Item=item)
    return _format_event(item)


def get_event(table, event_id: str, event_time: datetime) -> dict | None:
    """Look up a single event by its ID and time (needed to reconstruct PK/SK)."""
    pk       = _make_pk(event_time)
    sk_prefix = f"TIME#"

    response = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with(sk_prefix),
        FilterExpression=Attr("event_id").eq(event_id),
    )
    items = response.get("Items", [])
    return _format_event(items[0]) if items else None


def update_event(table, event_id: str, event_time: datetime, data: EventUpdate, user_id: str) -> dict | None:
    pk        = _make_pk(event_time)
    sk_prefix = "TIME#"

    # Find the existing item
    response = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with(sk_prefix),
        FilterExpression=Attr("event_id").eq(event_id),
    )
    items = response.get("Items", [])
    if not items:
        return None

    existing = items[0]
    now      = datetime.now(timezone.utc).isoformat()
    updates  = data.model_dump(exclude_unset=True)

    # If time is changing we need to delete old item and create new one
    # since PK/SK are based on time
    if "time" in updates:
        new_time = updates["time"]
        new_time_iso = new_time.astimezone(timezone.utc).isoformat()

        table.delete_item(Key={"PK": existing["PK"], "SK": existing["SK"]})

        new_item = {
            **existing,
            "PK":         _make_pk(new_time),
            "SK":         _make_sk(new_time, event_id),
            "time":       new_time_iso,
            "updated_at": now,
            **{k: v for k, v in updates.items() if k != "time"},
        }
        if "is_private" in updates:
            new_item["is_private"] = updates["is_private"]
        if "location" in updates:
            new_item["location"] = updates["location"]
        if "invited_users" in updates:
            new_item["invited_users"] = updates["invited_users"]

        table.put_item(Item=new_item)
        return _format_event(new_item)

    # No time change — do a regular update
    update_parts  = []
    expr_names    = {}
    expr_values   = {}

    field_map = {
        "location":      "location",
        "is_private":    "is_private",
        "invited_users": "invited_users",
    }

    for i, (field, db_field) in enumerate(field_map.items()):
        if field in updates:
            placeholder  = f"#f{i}"
            val_holder   = f":v{i}"
            update_parts.append(f"{placeholder} = {val_holder}")
            expr_names[placeholder]  = db_field
            expr_values[val_holder]  = updates[field]

    # Always update updated_at
    update_parts.append("#upd = :upd")
    expr_names["#upd"]  = "updated_at"
    expr_values[":upd"] = now

    response = table.update_item(
        Key={"PK": existing["PK"], "SK": existing["SK"]},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW",
    )
    return _format_event(response["Attributes"])


def delete_event(table, event_id: str, event_time: datetime, user_id: str) -> bool:
    pk        = _make_pk(event_time)
    sk_prefix = "TIME#"

    response = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with(sk_prefix),
        FilterExpression=Attr("event_id").eq(event_id),
    )
    items = response.get("Items", [])
    if not items:
        return False

    existing = items[0]

    # Only the creator can delete
    if existing.get("created_by") != user_id:
        return False

    table.delete_item(Key={"PK": existing["PK"], "SK": existing["SK"]})
    return True


def list_events(
    table,
    user_id:   str,
    date:      str | None = None,
    hours_window: int = 24,
) -> list[dict]:
    """
    Get events within a time window.
    - Public events: visible to everyone
    - Private events: only visible to creator or invited users
    - Default window: next 24 hours from now
    """
    now     = datetime.now(timezone.utc)
    central = now.astimezone(__import__("datetime").timezone(timedelta(hours=-5)))

    if date:
        # Query a specific date
        pk = f"EVENT#{date}"
        response = table.query(
            KeyConditionExpression=Key("PK").eq(pk),
        )
        all_items = response.get("Items", [])
    else:
        # Query today and tomorrow to cover the 24h window
        today    = central.strftime("%Y-%m-%d")
        tomorrow = (central + timedelta(days=1)).strftime("%Y-%m-%d")

        today_resp    = table.query(KeyConditionExpression=Key("PK").eq(f"EVENT#{today}"))
        tomorrow_resp = table.query(KeyConditionExpression=Key("PK").eq(f"EVENT#{tomorrow}"))
        all_items     = today_resp.get("Items", []) + tomorrow_resp.get("Items", [])

        # Filter to the time window
        window_end = central + timedelta(hours=hours_window)
        all_items  = [
            item for item in all_items
            if now <= datetime.fromisoformat(item["time"]) <= window_end
        ]

    # Filter by visibility
    visible = []
    for item in all_items:
        is_creator  = item.get("created_by") == user_id
        is_invited  = user_id in item.get("invited_users", [])
        is_public   = not item.get("is_private", False)

        if is_public or is_creator or is_invited:
            visible.append(_format_event(item))

    # Sort by time ascending
    visible.sort(key=lambda x: x["time"])
    return visible
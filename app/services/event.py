import uuid
from datetime import datetime, timezone, timedelta

from boto3.dynamodb.conditions import Key, Attr

from app.schemas.event import EventCreate, EventUpdate


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _make_pk(event_time: datetime) -> str:
    date_str = event_time.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return f"EVENT#{date_str}"


def _make_sk(event_time: datetime, event_id: str) -> str:
    time_str = event_time.astimezone(timezone.utc).isoformat()
    return f"TIME#{time_str}#ID#{event_id}"


def _make_invite_sk(event_time, event_id: str) -> str:
    if isinstance(event_time, str):
        event_time = datetime.fromisoformat(event_time)
    date_str = event_time.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return f"INVITE#{date_str}#{event_id}"


# ---------------------------------------------------------------------------
# Invite helpers
# ---------------------------------------------------------------------------

def _write_invites(table, event_item: dict, user_ids: list[str]):
    """Write INVITE# items for each user."""
    event_id   = event_item["event_id"]
    event_time = event_item["time"]
    location   = event_item["location"]
    created_by = event_item["created_by"]
    now        = datetime.now(timezone.utc).isoformat()
    sk         = _make_invite_sk(event_time, event_id)

    for user_id in user_ids:
        table.put_item(Item={
            "PK":         f"USER#{user_id}",
            "SK":         sk,
            "event_id":   event_id,
            "event_time": event_time,
            "location":   location,
            "status":     "pending",
            "invited_by": created_by,
            "created_at": now,
            "updated_at": now,
        })


def _delete_invites(table, event_id: str, event_time: str, user_ids: list[str]):
    """Delete INVITE# items for each user."""
    sk = _make_invite_sk(event_time, event_id)
    for user_id in user_ids:
        table.delete_item(Key={"PK": f"USER#{user_id}", "SK": sk})


def _get_invite_statuses(
    table, event_id: str, event_time: str, invited_users: list[str]
) -> list[dict]:
    """Fetch invite statuses for all invited users."""
    if not invited_users:
        return []

    sk       = _make_invite_sk(event_time, event_id)
    statuses = []

    for user_id in invited_users:
        item = table.get_item(
            Key={"PK": f"USER#{user_id}", "SK": sk}
        ).get("Item")
        statuses.append({
            "user_id": user_id,
            "status":  item.get("status", "pending") if item else "pending",
        })

    return statuses


# ---------------------------------------------------------------------------
# Event formatting
# ---------------------------------------------------------------------------

def _format_event(item: dict, invite_statuses: list[dict] = None) -> dict:
    return {
        "event_id":        item["event_id"],
        "location":        item["location"],
        "time":            item["time"],
        "is_private":      item.get("is_private", False),
        "invited_users":   item.get("invited_users", []),
        "invite_statuses": invite_statuses or [],
        "message":         item.get("message", ""),
        "created_by":      item["created_by"],
        "created_at":      item["created_at"],
        "updated_at":      item["updated_at"],
    }


# ---------------------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------------------

def create_event(table, data: EventCreate, user_id: str) -> dict:
    event_id = str(uuid.uuid4())
    now      = datetime.now(timezone.utc).isoformat()
    time_iso = data.time.astimezone(timezone.utc).isoformat()

    item = {
        "PK":            _make_pk(data.time),
        "SK":            _make_sk(data.time, event_id),
        "event_id":      event_id,
        "location":      data.location,
        "time":          time_iso,
        "is_private":    data.is_private,
        "invited_users": data.invited_users,
        "message":       data.message,
        "created_by":    user_id,
        "created_at":    now,
        "updated_at":    now,
    }
    table.put_item(Item=item)

    if data.invited_users:
        _write_invites(table, item, data.invited_users)

    invite_statuses = _get_invite_statuses(table, event_id, time_iso, data.invited_users)
    return _format_event(item, invite_statuses)


def get_event(table, event_id: str, event_time: datetime) -> dict | None:
    pk       = _make_pk(event_time)
    response = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("TIME#"),
        FilterExpression=Attr("event_id").eq(event_id),
    )
    items = response.get("Items", [])
    if not items:
        return None

    item            = items[0]
    invite_statuses = _get_invite_statuses(
        table, event_id, item["time"], item.get("invited_users", [])
    )
    return _format_event(item, invite_statuses)


def update_event(
    table, event_id: str, event_time: datetime, data: EventUpdate, user_id: str
) -> dict | None:
    pk       = _make_pk(event_time)
    response = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("TIME#"),
        FilterExpression=Attr("event_id").eq(event_id),
    )
    items = response.get("Items", [])
    if not items:
        return None

    existing = items[0]
    now      = datetime.now(timezone.utc).isoformat()
    updates  = data.model_dump(exclude_unset=True)

    # Handle invite list changes
    if "invited_users" in updates:
        old_invited = set(existing.get("invited_users", []))
        new_invited = set(updates["invited_users"])

        added   = new_invited - old_invited
        removed = old_invited - new_invited

        if added:
            temp_item = {**existing, **updates}
            _write_invites(table, temp_item, list(added))
        if removed:
            _delete_invites(table, event_id, existing["time"], list(removed))

    # Time change — delete old item, recreate with new keys
    if "time" in updates:
        new_time     = updates["time"]
        new_time_iso = new_time.astimezone(timezone.utc).isoformat()

        # Delete old invite items and recreate at new time
        old_invited = existing.get("invited_users", [])
        if old_invited:
            _delete_invites(table, event_id, existing["time"], old_invited)

        table.delete_item(Key={"PK": existing["PK"], "SK": existing["SK"]})

        new_item = {
            **existing,
            "PK":         _make_pk(new_time),
            "SK":         _make_sk(new_time, event_id),
            "time":       new_time_iso,
            "updated_at": now,
        }
        for field in ("location", "is_private", "invited_users"):
            if field in updates:
                new_item[field] = updates[field]

        table.put_item(Item=new_item)

        final_invited = new_item.get("invited_users", [])
        if final_invited:
            _write_invites(table, new_item, final_invited)

        invite_statuses = _get_invite_statuses(table, event_id, new_time_iso, final_invited)
        return _format_event(new_item, invite_statuses)

    # No time change — regular attribute update
    update_parts = []
    expr_names   = {}
    expr_values  = {}

    for i, (field, db_field) in enumerate({
        "location":      "location",
        "is_private":    "is_private",
        "invited_users": "invited_users",
    }.items()):
        if field in updates:
            ph = f"#f{i}"
            vh = f":v{i}"
            update_parts.append(f"{ph} = {vh}")
            expr_names[ph] = db_field
            expr_values[vh] = updates[field]

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
    updated_item    = response["Attributes"]
    final_invited   = updated_item.get("invited_users", [])
    invite_statuses = _get_invite_statuses(table, event_id, updated_item["time"], final_invited)
    return _format_event(updated_item, invite_statuses)


def delete_event(table, event_id: str, event_time: datetime, user_id: str) -> bool:
    pk       = _make_pk(event_time)
    response = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("TIME#"),
        FilterExpression=Attr("event_id").eq(event_id),
    )
    items = response.get("Items", [])
    if not items:
        return False

    existing = items[0]
    if existing.get("created_by") != user_id:
        return False

    # Clean up all INVITE items first
    invited_users = existing.get("invited_users", [])
    if invited_users:
        _delete_invites(table, event_id, existing["time"], invited_users)

    table.delete_item(Key={"PK": existing["PK"], "SK": existing["SK"]})
    return True


# ---------------------------------------------------------------------------
# Invite actions
# ---------------------------------------------------------------------------

def respond_to_invite(
    table, user_id: str, event_id: str, event_time: datetime, status: str
) -> str:
    """
    Accept or decline an invite.
    Returns: 'not_found' | 'not_invited' | 'ok'
    """
    pk       = _make_pk(event_time)
    response = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("TIME#"),
        FilterExpression=Attr("event_id").eq(event_id),
    )
    items = response.get("Items", [])
    if not items:
        return "not_found"

    event = items[0]

    if user_id not in event.get("invited_users", []):
        return "not_invited"

    now = datetime.now(timezone.utc).isoformat()
    sk  = _make_invite_sk(event["time"], event_id)

    # Check if invite item exists — update or create
    existing_invite = table.get_item(
        Key={"PK": f"USER#{user_id}", "SK": sk}
    ).get("Item")

    if existing_invite:
        table.update_item(
            Key={"PK": f"USER#{user_id}", "SK": sk},
            UpdateExpression="SET #s = :s, updated_at = :ua",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status, ":ua": now},
        )
    else:
        # Invite item was never created — create it now with response status
        table.put_item(Item={
            "PK":         f"USER#{user_id}",
            "SK":         sk,
            "event_id":   event_id,
            "event_time": event["time"],
            "location":   event["location"],
            "status":     status,
            "invited_by": event["created_by"],
            "created_at": now,
            "updated_at": now,
        })

    return "ok"


def get_user_invites(
    table, user_id: str, status_filter: str | None = None
) -> list[dict]:
    """Get all invites for a user, optionally filtered by status."""
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("INVITE#"),
    )
    items = response.get("Items", [])

    if status_filter:
        items = [item for item in items if item.get("status") == status_filter]

    return [
        {
            "event_id":   item["event_id"],
            "event_time": item["event_time"],
            "location":   item["location"],
            "status":     item.get("status", "pending"),
            "invited_by": item.get("invited_by", ""),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }
        for item in items
    ]


# ---------------------------------------------------------------------------
# List events
# ---------------------------------------------------------------------------

def list_events(
    table,
    user_id:      str,
    date:         str | None = None,
    hours_window: int = 24,
) -> list[dict]:
    now = datetime.now(timezone.utc)

    if date:
        pk        = f"EVENT#{date}"
        response  = table.query(KeyConditionExpression=Key("PK").eq(pk))
        all_items = response.get("Items", [])
    else:
        today    = now.strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

        all_items = (
            table.query(KeyConditionExpression=Key("PK").eq(f"EVENT#{today}")).get("Items", [])
            + table.query(KeyConditionExpression=Key("PK").eq(f"EVENT#{tomorrow}")).get("Items", [])
        )

        window_end = now + timedelta(hours=hours_window)
        all_items  = [
            item for item in all_items
            if now <= datetime.fromisoformat(item["time"]) <= window_end
        ]

    visible = []
    for item in all_items:
        is_creator = item.get("created_by") == user_id
        is_invited = user_id in item.get("invited_users", [])
        is_public  = not item.get("is_private", False)

        if is_public or is_creator or is_invited:
            invite_statuses = _get_invite_statuses(
                table, item["event_id"], item["time"], item.get("invited_users", [])
            )
            visible.append(_format_event(item, invite_statuses))

    visible.sort(key=lambda x: x["time"])
    return visible
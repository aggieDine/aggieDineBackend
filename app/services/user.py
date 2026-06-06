from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr, Key

from app.schemas.user import AllergenUpdate, DietUpdate, UserCreate, UserUpdate



# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _pk(user_id: str) -> str:
    return f"USER#{user_id}"


def _format_profile(item: dict, follower_count: int, following_count: int) -> dict:
    return {
        "user_id":             item["user_id"],
        "display_name":        item["display_name"],
        "email":               item["email"],
        "dietary_preferences": item.get("dietary_preferences", []),
        "allergens":           item.get("allergens", []),
        "fcm_token":           item.get("fcm_token"),
        "follower_count":      follower_count,
        "following_count":     following_count,
        "created_at":          item["created_at"],
    }


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def create_user(table, user_id: str, data: UserCreate) -> dict | None:
    """Create user profile. Returns None if already exists (409)."""
    existing = table.get_item(
        Key={"PK": _pk(user_id), "SK": "PROFILE"}
    ).get("Item")

    if existing:
        return None

    now  = datetime.now(timezone.utc).isoformat()
    item = {
        "PK":                  _pk(user_id),
        "SK":                  "PROFILE",
        "user_id":             user_id,
        "display_name":        data.display_name,
        "email":               data.email,
        "dietary_preferences": [],
        "allergens":           [],
        "fcm_token":           None,
        "created_at":          now,
        "updated_at":          now,
    }
    table.put_item(Item=item)
    return _format_profile(item, 0, 0)


def get_user(table, user_id: str) -> dict | None:
    """Get user profile with follower/following counts."""
    item = table.get_item(
        Key={"PK": _pk(user_id), "SK": "PROFILE"}
    ).get("Item")

    if not item:
        return None

    follower_count = table.query(
        KeyConditionExpression=Key("PK").eq(_pk(user_id)) & Key("SK").begins_with("FOLLOWER#"),
        Select="COUNT",
    ).get("Count", 0)

    following_count = table.query(
        KeyConditionExpression=Key("PK").eq(_pk(user_id)) & Key("SK").begins_with("FOLLOWING#"),
        Select="COUNT",
    ).get("Count", 0)

    return _format_profile(item, follower_count, following_count)


def update_user(table, user_id: str, data: UserUpdate) -> dict | None:
    """Update display_name and/or email. Only provided fields are changed."""
    updates = data.model_dump(exclude_unset=True)

    # Nothing provided — just return current profile
    if not updates:
        return get_user(table, user_id)

    existing = table.get_item(
        Key={"PK": _pk(user_id), "SK": "PROFILE"}
    ).get("Item")

    if not existing:
        return None

    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now

    # Build UpdateExpression dynamically from provided fields
    update_parts = []
    expr_names   = {}
    expr_values  = {}

    for i, (field, value) in enumerate(updates.items()):
        placeholder = f"#f{i}"
        val_holder  = f":v{i}"
        update_parts.append(f"{placeholder} = {val_holder}")
        expr_names[placeholder] = field
        expr_values[val_holder] = value

    response = table.update_item(
        Key={"PK": _pk(user_id), "SK": "PROFILE"},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW",
    )
    return _format_profile(response["Attributes"], 0, 0)


def delete_user(table, user_id: str) -> bool:
    """
    Delete user account and cascade-remove all follow relationships.
    Returns False if user not found.
    """
    existing = table.get_item(
        Key={"PK": _pk(user_id), "SK": "PROFILE"}
    ).get("Item")

    if not existing:
        return False

    # Everyone this user follows
    following_items = table.query(
        KeyConditionExpression=Key("PK").eq(_pk(user_id)) & Key("SK").begins_with("FOLLOWING#"),
    ).get("Items", [])

    # Everyone who follows this user
    follower_items = table.query(
        KeyConditionExpression=Key("PK").eq(_pk(user_id)) & Key("SK").begins_with("FOLLOWER#"),
    ).get("Items", [])

    # Collect all keys to delete
    keys_to_delete = [{"PK": _pk(user_id), "SK": "PROFILE"}]

    for item in following_items:
        followed_id = item["followed_id"]
        # This user's own FOLLOWING# item
        keys_to_delete.append({"PK": _pk(user_id),      "SK": f"FOLLOWING#{followed_id}"})
        # Reverse FOLLOWER# item on the followed user's partition
        keys_to_delete.append({"PK": _pk(followed_id),  "SK": f"FOLLOWER#{user_id}"})

    for item in follower_items:
        follower_id = item["follower_id"]
        # This user's own FOLLOWER# item
        keys_to_delete.append({"PK": _pk(user_id),      "SK": f"FOLLOWER#{follower_id}"})
        # Reverse FOLLOWING# item on the follower's partition
        keys_to_delete.append({"PK": _pk(follower_id),  "SK": f"FOLLOWING#{user_id}"})

    # Deduplicate
    seen         = set()
    unique_keys  = []
    for key in keys_to_delete:
        k = (key["PK"], key["SK"])
        if k not in seen:
            seen.add(k)
            unique_keys.append(key)

    # Batch delete (batch_writer handles chunking automatically)
    with table.batch_writer() as batch:
        for key in unique_keys:
            batch.delete_item(Key=key)

    return True


def search_users(table, query: str, limit: int = 20) -> list[dict]:
    """
    Search users by display_name (case-insensitive partial match).
    Uses a scan — fine at this scale, add a GSI later if needed.
    """
    response = table.scan(
        FilterExpression=Attr("SK").eq("PROFILE"),
    )

    query_lower = query.lower()
    results = [
        {"user_id": item["user_id"], "display_name": item["display_name"]}
        for item in response.get("Items", [])
        if query_lower in item.get("display_name", "").lower()
    ]

    return results[:limit]


# ---------------------------------------------------------------------------
# Follow / Unfollow
# ---------------------------------------------------------------------------

def follow_user(table, follower_id: str, followed_id: str) -> str:
    """Returns: 'not_found' | 'already_following' | 'ok'"""
    target = table.get_item(
        Key={"PK": _pk(followed_id), "SK": "PROFILE"}
    ).get("Item")
    if not target:
        return "not_found"

    existing = table.get_item(
        Key={"PK": _pk(follower_id), "SK": f"FOLLOWING#{followed_id}"}
    ).get("Item")
    if existing:
        return "already_following"

    now = datetime.now(timezone.utc).isoformat()

    table.put_item(Item={
        "PK":          _pk(follower_id),
        "SK":          f"FOLLOWING#{followed_id}",
        "follower_id": follower_id,
        "followed_id": followed_id,
        "created_at":  now,
    })
    table.put_item(Item={
        "PK":          _pk(followed_id),
        "SK":          f"FOLLOWER#{follower_id}",
        "follower_id": follower_id,
        "followed_id": followed_id,
        "created_at":  now,
    })
    return "ok"


def unfollow_user(table, follower_id: str, followed_id: str) -> str:
    """Returns: 'not_following' | 'ok'"""
    existing = table.get_item(
        Key={"PK": _pk(follower_id), "SK": f"FOLLOWING#{followed_id}"}
    ).get("Item")

    if not existing:
        return "not_following"

    table.delete_item(Key={"PK": _pk(follower_id), "SK": f"FOLLOWING#{followed_id}"})
    table.delete_item(Key={"PK": _pk(followed_id), "SK": f"FOLLOWER#{follower_id}"})
    return "ok"


# ---------------------------------------------------------------------------
# Followers / Following lists
# ---------------------------------------------------------------------------

def _get_user_summaries(table, user_ids: list[str]) -> list[dict]:
    summaries = []
    for uid in user_ids:
        item = table.get_item(
            Key={"PK": _pk(uid), "SK": "PROFILE"},
            ProjectionExpression="user_id, display_name",
        ).get("Item")
        if item:
            summaries.append({
                "user_id":      item["user_id"],
                "display_name": item["display_name"],
            })
    return summaries


def get_followers(table, user_id: str) -> list[dict]:
    response     = table.query(
        KeyConditionExpression=Key("PK").eq(_pk(user_id)) & Key("SK").begins_with("FOLLOWER#"),
    )
    follower_ids = [item["follower_id"] for item in response.get("Items", [])]
    return _get_user_summaries(table, follower_ids)


def get_following(table, user_id: str) -> list[dict]:
    response     = table.query(
        KeyConditionExpression=Key("PK").eq(_pk(user_id)) & Key("SK").begins_with("FOLLOWING#"),
    )
    followed_ids = [item["followed_id"] for item in response.get("Items", [])]
    return _get_user_summaries(table, followed_ids)


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def update_diet(table, user_id: str, data: DietUpdate) -> dict | None:
    existing = table.get_item(
        Key={"PK": _pk(user_id), "SK": "PROFILE"}
    ).get("Item")
    if not existing:
        return None

    now = datetime.now(timezone.utc).isoformat()
    response = table.update_item(
        Key={"PK": _pk(user_id), "SK": "PROFILE"},
        UpdateExpression="SET dietary_preferences = :dp, updated_at = :ua",
        ExpressionAttributeValues={":dp": data.dietary_preferences, ":ua": now},
        ReturnValues="ALL_NEW",
    )
    return _format_profile(response["Attributes"], 0, 0)


def update_allergens(table, user_id: str, data: AllergenUpdate) -> dict | None:
    existing = table.get_item(
        Key={"PK": _pk(user_id), "SK": "PROFILE"}
    ).get("Item")
    if not existing:
        return None

    now = datetime.now(timezone.utc).isoformat()
    response = table.update_item(
        Key={"PK": _pk(user_id), "SK": "PROFILE"},
        UpdateExpression="SET allergens = :al, updated_at = :ua",
        ExpressionAttributeValues={":al": data.allergens, ":ua": now},
        ReturnValues="ALL_NEW",
    )
    return _format_profile(response["Attributes"], 0, 0)
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from app.schemas.example import ItemCreate, ItemUpdate


def create_item(table, data: ItemCreate) -> dict:
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "PK": f"ITEM#{item_id}",
        "SK": f"ITEM#{item_id}",
        "id": item_id,
        "name": data.name,
        "description": data.description,
        "created_at": now,
        "updated_at": now,
    }
    table.put_item(Item=item)
    return item


def get_item(table, item_id: str) -> dict | None:
    response = table.get_item(
        Key={"PK": f"ITEM#{item_id}", "SK": f"ITEM#{item_id}"}
    )
    return response.get("Item")


def list_items(table, limit: int = 20) -> list[dict]:
    response = table.query(
        KeyConditionExpression=Key("PK").begins_with("ITEM#"),
        Limit=limit,
    )
    return response.get("Items", [])


def update_item(table, item_id: str, data: ItemUpdate) -> dict | None:
    existing = get_item(table, item_id)
    if existing is None:
        return None

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return existing

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    update_expr_parts = []
    expr_attr_names = {}
    expr_attr_values = {}
    for i, (field, value) in enumerate(updates.items()):
        placeholder = f"#f{i}"
        val_placeholder = f":v{i}"
        update_expr_parts.append(f"{placeholder} = {val_placeholder}")
        expr_attr_names[placeholder] = field
        expr_attr_values[val_placeholder] = value

    response = table.update_item(
        Key={"PK": f"ITEM#{item_id}", "SK": f"ITEM#{item_id}"},
        UpdateExpression="SET " + ", ".join(update_expr_parts),
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values,
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def delete_item(table, item_id: str) -> bool:
    existing = get_item(table, item_id)
    if existing is None:
        return False
    table.delete_item(Key={"PK": f"ITEM#{item_id}", "SK": f"ITEM#{item_id}"})
    return True

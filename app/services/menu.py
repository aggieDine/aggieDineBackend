import json
from datetime import datetime, timezone, timedelta

from boto3.dynamodb.conditions import Key

from app.config import settings


def get_latest_scrape_key(table, date: str) -> str | None:
    """Query DynamoDB for the most recent scrape S3 key for a given date."""
    from boto3.dynamodb.conditions import Key
    
    response = table.query(
        KeyConditionExpression=Key("PK").eq("SCRAPE#latest") & Key("SK").begins_with(f"SCRAPE#{date}"),
        ScanIndexForward=False,
        Limit=1,
    )
    items = response.get("Items", [])
    print(f"[DEBUG] DynamoDB query for date {date} returned {len(items)} items")
    if items:
        print(f"[DEBUG] Found s3_key: {items[0].get('s3_key')}")
    
    if not items:
        return None
    return items[0].get("s3_key")


def fetch_menu_from_s3(s3_client, s3_key: str) -> dict:
    """Download and parse the menu JSON from S3."""
    response = s3_client.get_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=s3_key,
    )
    return json.loads(response["Body"].read().decode("utf-8"))


def filter_menus(
    data: dict,
    location: str | None,
    period: str | None,
    filters: list[str] | None,
) -> dict:
    """Filter the menu data based on query params."""
    menus = data.get("menus", [])

    # Filter by location name (case-insensitive partial match)
    if location:
        menus = [
            m for m in menus
            if location.lower() in m["location_name"].lower()
        ]

    # Filter by period name (case-insensitive)
    if period:
        menus = [
            m for m in menus
            if period.lower() == m["period_name"].lower()
        ]

    # Filter items by filters (item must have ALL requested filters)
    if filters:
        filters_lower = [f.lower() for f in filters]
        filtered_menus = []
        for menu in menus:
            filtered_items = [
                item for item in menu["items"]
                if all(
                    any(f == item_filter.lower() for item_filter in item["filters"])
                    for f in filters_lower
                )
            ]
            if filtered_items:
                filtered_menus.append({**menu, "items": filtered_items, "item_count": len(filtered_items)})
        menus = filtered_menus

    return {
        **data,
        "menus": menus,
        "location_count": len(set(m["location_name"] for m in menus)),
        "total_items": sum(m["item_count"] for m in menus),
    }


def get_menu(
    table,
    s3_client,
    date: str | None,
    location: str | None,
    period: str | None,
    filters: list[str] | None,
) -> dict | None:
    # Default to today in CST
    if not date:
        central = timezone(timedelta(hours=-5))
        date = datetime.now(central).strftime("%Y-%m-%d")

    s3_key = get_latest_scrape_key(table, date)
    if not s3_key:
        return None

    data = fetch_menu_from_s3(s3_client, s3_key)
    return filter_menus(data, location, period, filters)
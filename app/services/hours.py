import json
from datetime import datetime, timezone, timedelta

from boto3.dynamodb.conditions import Key, Attr

from app.config import settings


def get_latest_hours_key(table, date: str) -> str | None:
    """Query DynamoDB for the most recent hours scrape S3 key for a given date."""
    response = table.query(
        KeyConditionExpression=Key("PK").eq("SCRAPE_HOURS#latest"),
        FilterExpression=Attr("date").eq(date),
        ScanIndexForward=False,
    )
    items = response.get("Items", [])
    if not items:
        return None
    items.sort(key=lambda x: x.get("scraped_at", ""), reverse=True)
    return items[0].get("s3_key")


def fetch_hours_from_s3(s3_client, s3_key: str) -> dict:
    """Download and parse the hours JSON from S3."""
    response = s3_client.get_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=s3_key,
    )
    return json.loads(response["Body"].read().decode("utf-8"))


def get_hours(
    table,
    s3_client,
    date: str | None
) -> dict | None:
    # Default to today in CST
    if not date:
        central = timezone(timedelta(hours=-5))
        date = datetime.now(central).strftime("%Y-%m-%d")

    s3_key = get_latest_hours_key(table, date)
    if not s3_key:
        return None

    data = fetch_hours_from_s3(s3_client, s3_key)

    return data
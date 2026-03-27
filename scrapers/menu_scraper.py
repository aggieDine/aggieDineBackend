"""
Standalone Lambda handler for scheduled menu scraping.

Triggered by EventBridge every 30 minutes (configured in template.yaml).
Replace the placeholder logic below with your actual scraping implementation.
"""

import json
import os
from datetime import datetime, timezone

import boto3


def handler(event, context):
    table_name = os.environ.get("DYNAMODB_TABLE_NAME")
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    region = os.environ.get("AWS_REGION", "us-east-1")

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)
    s3 = boto3.client("s3", region_name=region)

    now = datetime.now(timezone.utc).isoformat()

    # --- Placeholder: replace with real scraping logic ---
    scraped_data = {
        "scraped_at": now,
        "source": "placeholder",
        "menus": [],
    }

    # Write to S3 as JSON cache
    s3.put_object(
        Bucket=bucket_name,
        Key=f"scrapes/{now}.json",
        Body=json.dumps(scraped_data),
        ContentType="application/json",
    )

    # Write a record to DynamoDB
    table.put_item(
        Item={
            "PK": "SCRAPE#latest",
            "SK": f"SCRAPE#{now}",
            "scraped_at": now,
            "source": "placeholder",
            "item_count": 0,
        }
    )

    return {"statusCode": 200, "body": json.dumps({"scraped_at": now})}

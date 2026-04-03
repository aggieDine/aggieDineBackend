"""
Lambda handler for scheduled TAMU dining menu scraping.
Triggered by EventBridge every 30 minutes (configured in template.yaml).

Dependencies (add to your Lambda layer or requirements.txt):
  - curl_cffi
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta

import boto3
from curl_cffi import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_API  = "https://apiv4.dineoncampus.com"
SITE_ID   = "5751fd4290975b60e0489534"

REQUEST_DELAY_SECONDS = 1

session = requests.Session(impersonate="chrome110")
session.headers.update({
    "Accept":             "application/json, text/plain, */*",
    "Accept-Language":    "en-US,en;q=0.9",
    "Referer":            "https://dineoncampus.com/",
    "User-Agent":         "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "sec-ch-ua":          '"Chromium";v="147", "Not.A/Brand";v="8"',
    "sec-ch-ua-mobile":   "?0",
    "sec-ch-ua-platform": '"macOS"',
})

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> dict:
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[Error] {url}: {e}")
        return {}


def fetch_locations() -> list:
    url  = f"{BASE_API}/sites/{SITE_ID}/locations-public?for_menus=true"
    data = _get(url)
    locations = []
    for building in data.get("buildings", []):
        locations.extend(building.get("locations", []))
    return locations


def fetch_periods(location_id: str, date_str: str) -> list:
    url  = f"{BASE_API}/locations/{location_id}/periods/?date={date_str}"
    data = _get(url)
    time.sleep(REQUEST_DELAY_SECONDS)
    return data.get("periods", [])


def fetch_menu(location_id: str, period_id: str, date_str: str) -> dict:
    url  = f"{BASE_API}/locations/{location_id}/menu?date={date_str}&period={period_id}"
    data = _get(url)
    time.sleep(REQUEST_DELAY_SECONDS)
    return data


def is_closed(menu_data: dict) -> bool:
    return menu_data.get("closedOnDate", False)


def parse_menu_items(menu_data: dict) -> list:
    items      = []
    categories = menu_data.get("period", {}).get("categories", [])
    for category in categories:
        station = category.get("name", "Unknown Station")
        for item in category.get("items", []):
            allergens = [f["name"] for f in item.get("filters", []) if f.get("type") == "allergen"]
            labels    = [f["name"] for f in item.get("filters", []) if f.get("type") == "label"]
            nutrients = [
                {"name": n.get("name"), "value": n.get("value"), "unit": n.get("uom")}
                for n in item.get("nutrients", [])
            ]
            items.append({
                "name":        item.get("name", ""),
                "station":     station,
                "description": item.get("desc", ""),
                "portion":     item.get("portion", ""),
                "ingredients": item.get("ingredients", ""),
                "calories":    item.get("calories", ""),
                "allergens":   allergens,
                "labels":      labels,
                "nutrients":   nutrients,
            })
    return items


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def handler(event, context):
    table_name = os.environ.get("DYNAMODB_TABLE_NAME")
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    region = os.environ.get("AWS_REGION", "us-east-2")

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table    = dynamodb.Table(table_name)
    s3       = boto3.client("s3", region_name=region)

    now     = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    central = timezone(timedelta(hours=-5))  # CST; change to -4 for CDT
    today   = now.astimezone(central).strftime("%Y-%m-%d")

    # ---- 1. Fetch all locations -------------------------------------------
    locations = fetch_locations()
    if not locations:
        print("No locations returned — aborting.")
        return {"statusCode": 500, "body": json.dumps({"error": "no locations"})}

    # ---- 2. Loop locations → periods → items ------------------------------
    all_menus   = []
    total_items = 0
    skipped     = 0

    for location in locations:
        loc_id   = str(location.get("id") or location.get("_id", ""))
        loc_name = location.get("name", "Unknown")
        if not loc_id:
            continue

        periods = fetch_periods(loc_id, today)

        for period in periods:
            period_id   = str(period.get("id") or period.get("_id", ""))
            period_name = period.get("name", "Unknown Period")
            if not period_id:
                continue

            menu_data = fetch_menu(loc_id, period_id, today)

            if is_closed(menu_data):
                skipped += 1
                continue

            items = parse_menu_items(menu_data)
            total_items += len(items)

            all_menus.append({
                "location_id":   loc_id,
                "location_name": loc_name,
                "date":          today,
                "period_id":     period_id,
                "period_name":   period_name,
                "item_count":    len(items),
                "items":         items,
            })

    # ---- 3. Build final payload -------------------------------------------
    scraped_data = {
        "scraped_at":          now_iso,
        "source":              "dineoncampus.com/tamu",
        "date":                today,
        "location_count":      len(locations),
        "total_menu_entries":  len(all_menus),
        "total_items":         total_items,
        "skipped_closed":      skipped,
        "menus":               all_menus,
    }

    # ---- 4. Write full JSON blob to S3 ------------------------------------
    s3_key = f"scrapes/{today}/{now_iso}.json"
    s3.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=json.dumps(scraped_data, indent=2),
        ContentType="application/json",
    )
    print(f"Wrote to s3://{bucket_name}/{s3_key}")

    # ---- 5. Write summary record to DynamoDB ------------------------------
    table.put_item(
        Item={
            "PK":                  "SCRAPE#latest",
            "SK":                  f"SCRAPE#{now_iso}",
            "scraped_at":          now_iso,
            "source":              "dineoncampus.com/tamu",
            "date":                today,
            "location_count":      len(locations),
            "total_menu_entries":  len(all_menus),
            "total_items":         total_items,
            "skipped_closed":      skipped,
            "s3_key":              s3_key,
        }
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "scraped_at":     now_iso,
            "locations":      len(locations),
            "menu_entries":   len(all_menus),
            "total_items":    total_items,
            "skipped_closed": skipped,
        }),
    }
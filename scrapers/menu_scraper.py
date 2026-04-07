"""
Lambda handler for scheduled TAMU dining menu scraping.
Triggered by EventBridge every day at 2:00am (configured in template.yaml).

Dependencies (add to your Lambda layer or requirements.txt):
  - curl_cffi
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
import random

import boto3
from curl_cffi import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_API  = "https://apiv4.dineoncampus.com"
SITE_ID   = "5751fd4290975b60e0489534"

# 1. Format the ScraperAPI URL
SCRAPERAPI_KEY = os.environ.get("SCRAPERAPI_KEY", "YOUR_API_KEY_HERE")
# Note: Requires http:// at the front for request libraries
PROXY_URL = "http://sqhmhfry:to40ugbwi9ea@p.webshare.io:80"

WEBSHARE_CREDENTIALS = "sqhmhfry:to40ugbwi9ea"
WEBSHARE_IPS = [
    "31.59.20.176:6754",
    "23.95.150.145:6114",
    "198.23.239.134:6540",
    "45.38.107.97:6014",
    "107.172.163.27:6543",
    "198.105.121.200:6462",
    "216.10.27.159:6837",
    "142.111.67.146:5611",
    "191.96.254.138:6185",
    "31.58.9.4:6077"
]

REQUEST_DELAY_SECONDS = 1

session = requests.Session(
    impersonate="chrome110",
    verify=False # Keep this here! Webshare needs it just like ScraperAPI did
)
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

def _get(url: str, retries=3) -> dict:
    for attempt in range(retries):
        # 1. Pick a random IP from your list for this attempt
        proxy_ip = random.choice(WEBSHARE_IPS)
        proxy_url = f"http://{WEBSHARE_CREDENTIALS}@{proxy_ip}"
        
        try:
            # 2. Inject the specific proxy directly into the request
            resp = session.get(
                url, 
                timeout=120, 
                proxies={"http": proxy_url, "https": proxy_url}
            )
            resp.raise_for_status()
            return resp.json()
            
        except Exception as e:
            print(f"[Warning] Attempt {attempt + 1} failed for {url} using {proxy_ip}: {e}")
            if attempt < retries - 1:
                time.sleep(3) 
            else:
                print(f"[Error] Final failure for {url}. Skipping.")
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
            # All filters (allergens, diet labels, etc.) — no type field exists
            filters = [f["name"] for f in item.get("filters", [])]
            calories_raw = item.get("calories", "")
            calories = int(calories_raw) if calories_raw != "" and calories_raw is not None else None
            
            nutrients = [
                {
                    "name":          n.get("name"),
                    "value":         n.get("value"),
                    "unit":          n.get("uom"),
                    "value_numeric": n.get("valueNumeric"),
                }
                for n in item.get("nutrients", [])
                if n.get("value") and n.get("value") != "-"  # skip empty values
            ]

            items.append({
                "id":          item.get("id", ""),
                "name":        item.get("name", ""),
                "station":     station,
                "description": item.get("desc", ""),
                "portion":     item.get("portion", ""),
                "ingredients": item.get("ingredients", ""),
                "calories": calories,
                "filters":     filters,   # contains allergens + diet labels + icons
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
                "location_id":      loc_id,
                "location_name":    loc_name,
                "date":             today,
                "period_id":        period_id,
                "period_name":      period_name,
                "item_count":       len(items),
                "items":            items,
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
    s3_key = f"scrapes/menu/{today}/{now_iso}.json"
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
"""
Lambda handler for scheduled TAMU dining menu scraping.
Triggered by EventBridge every 30 minutes (configured in template.yaml).

Dependencies (add to your Lambda layer or requirements.txt):
  - cloudscraper
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import boto3
import cloudscraper

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_API_V1 = "https://api.dineoncampus.com"
BASE_API_V4 = "https://apiv4.dineoncampus.com"
SITE_ID     = "5751fd4290975b60e0489534"

REQUEST_DELAY_SECONDS = 0.3
MAX_WORKERS = 5

session = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "darwin", "mobile": False},
)
session.headers.update({
    "Accept":             "application/json, text/plain, */*",
    "Accept-Language":    "en-US,en;q=0.9",
    "Referer":            "https://dineoncampus.com/",
})

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> dict:
    try:
        time.sleep(REQUEST_DELAY_SECONDS)
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[Error] {url}: {e}")
        return {}


def fetch_locations() -> list:
    # Try V1 first, fall back to V4
    url_v1 = f"{BASE_API_V1}/v1/locations/all_locations?platform=0&site_id={SITE_ID}&for_menus=true&with_buildings=true"
    data = _get(url_v1)
    if data:
        locations = []
        for building in data.get("buildings", []):
            locations.extend(building.get("locations", []))
        if locations:
            return locations

    print("[Fallback] V1 failed, trying V4...")
    url_v4 = f"{BASE_API_V4}/sites/{SITE_ID}/locations-public?for_menus=true"
    data = _get(url_v4)
    locations = []
    for building in data.get("buildings", []):
        locations.extend(building.get("locations", []))
    return locations


def fetch_periods(location_id: str, date_str: str) -> list:
    url = f"{BASE_API_V1}/v1/location/{location_id}/periods?platform=0&date={date_str}"
    data = _get(url)
    if data.get("periods"):
        return data["periods"]

    url = f"{BASE_API_V4}/locations/{location_id}/periods/?date={date_str}"
    data = _get(url)
    return data.get("periods", [])


def fetch_menu(location_id: str, period_id: str, date_str: str) -> dict:
    url = f"{BASE_API_V1}/v1/location/{location_id}/periods/{period_id}?platform=0&date={date_str}"
    data = _get(url)
    if data:
        return data

    url = f"{BASE_API_V4}/locations/{location_id}/menu?date={date_str}&period={period_id}"
    return _get(url)


def is_open(location: dict) -> bool:
    status = location.get("status", {})
    if isinstance(status, dict):
        return status.get("label", "").lower() == "open"
    return False


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
# Parallel fetch helpers
# ---------------------------------------------------------------------------

def _fetch_location_periods(location: dict, today: str) -> dict:
    """Fetch periods for a single location. Returns location info + periods."""
    loc_id   = str(location.get("id") or location.get("_id", ""))
    loc_name = location.get("name", "Unknown")
    if not loc_id:
        return None
    try:
        periods = fetch_periods(loc_id, today)
        return {"loc_id": loc_id, "loc_name": loc_name, "periods": periods}
    except Exception as e:
        print(f"[Error] periods for {loc_name}: {e}")
        return None


def _fetch_menu_entry(loc_id: str, loc_name: str, period: dict, today: str) -> dict:
    """Fetch and parse menu for a single location+period. Returns menu entry or None."""
    period_id   = str(period.get("id") or period.get("_id", ""))
    period_name = period.get("name", "Unknown Period")
    if not period_id:
        return None
    try:
        menu_data = fetch_menu(loc_id, period_id, today)
        if is_closed(menu_data):
            return {"skipped": True}
        items = parse_menu_items(menu_data)
        return {
            "location_id":   loc_id,
            "location_name": loc_name,
            "date":          today,
            "period_id":     period_id,
            "period_name":   period_name,
            "item_count":    len(items),
            "items":         items,
        }
    except Exception as e:
        print(f"[Error] menu for {loc_name}/{period_name}: {e}")
        return None


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

    print(f"Found {len(locations)} locations")

    # ---- 2. Fetch periods in parallel ------------------------------------
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        period_futures = {
            executor.submit(_fetch_location_periods, loc, today): loc
            for loc in locations
        }
        location_periods = []
        for future in as_completed(period_futures):
            result = future.result()
            if result and result["periods"]:
                location_periods.append(result)

    print(f"Fetched periods for {len(location_periods)} locations")

    # ---- 3. Fetch menus in parallel --------------------------------------
    all_menus   = []
    total_items = 0
    skipped     = 0

    menu_tasks = []
    for lp in location_periods:
        for period in lp["periods"]:
            menu_tasks.append((lp["loc_id"], lp["loc_name"], period, today))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        menu_futures = {
            executor.submit(_fetch_menu_entry, *task): task
            for task in menu_tasks
        }
        for future in as_completed(menu_futures):
            result = future.result()
            if result is None:
                continue
            if result.get("skipped"):
                skipped += 1
                continue
            total_items += result["item_count"]
            all_menus.append(result)

    print(f"Fetched {len(all_menus)} menus, {total_items} items, skipped {skipped} closed")

    # ---- 4. Build final payload -------------------------------------------
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

    # ---- 5. Write full JSON blob to S3 ------------------------------------
    s3_key = f"scrapes/{today}/{now_iso}.json"
    s3.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=json.dumps(scraped_data, indent=2),
        ContentType="application/json",
    )
    print(f"Wrote to s3://{bucket_name}/{s3_key}")

    # ---- 6. Write summary record to DynamoDB ------------------------------
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


if __name__ == "__main__":
    result = handler({}, None)
    print(result)
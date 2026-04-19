"""
Lambda handler for scheduled TAMU dining HOURS scraping.
Triggered by EventBridge every day at 2:00am (configured in template.yaml).
Scrapes hours for exactly 7 days from now and saves to S3.

Uses Playwright with proxy rotation to bypass bot protection.
"""

import os
import json
import re
import time
import random
from datetime import datetime, timezone, timedelta

import boto3
from bs4 import BeautifulSoup

os.environ["HOME"] = "/tmp"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/ms-playwright"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
URL = "https://dineoncampus.com/tamu/hours-of-operation"

WEBSHARE_CREDENTIALS = os.environ.get("WEBSHARE_CREDENTIALS")
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
    "31.58.9.4:6077",
]

# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------

def get_proxy() -> dict:
    """Pick a random Webshare proxy and return Playwright proxy config."""
    ip_port  = random.choice(WEBSHARE_IPS)
    user, pw = WEBSHARE_CREDENTIALS.split(":")
    return {
        "server":   f"http://{ip_port}",
        "username": user,
        "password": pw,
    }


def make_context(playwright, proxy: dict):
    """Launch a stealth browser context that mimics a real Mac Chrome user."""
    browser = playwright.chromium.launch(
        headless=True,
        proxy=proxy,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-gpu",
            "--no-zygote",
            "--single-process",
            "--window-size=1920,1080",
        ],
    )

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/Chicago",
        # Mimic real browser fingerprint
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "sec-ch-ua":       '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "sec-ch-ua-mobile":   "?0",
            "sec-ch-ua-platform": '"macOS"',
        },
    )

    # Inject stealth JS to hide automation signals
    context.add_init_script("""
        // Hide webdriver flag
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        // Fake plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Fake language
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Fake chrome object
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };

        // Override permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)

    return browser, context


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def get_week_dates(html: str) -> list[str]:
    """Extract the 7 dates for the currently displayed week."""
    soup       = BeautifulSoup(html, "html.parser")
    heading_el = soup.find(string=re.compile(r"Week of"))

    if not heading_el:
        today  = datetime.now()
        sunday = today - timedelta(days=(today.weekday() + 1) % 7)
        return [(sunday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    m = re.search(r"Week of (\w+ \d+)\w*, (\d{4})", heading_el.strip())
    if m:
        try:
            start = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%B %d %Y")
            return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        except ValueError:
            pass

    today  = datetime.now()
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    return [(sunday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]


def scrape_target_date(html: str, week_dates: list[str], target_date: str) -> list[dict]:
    """Extract hours for the target date column only."""
    if target_date not in week_dates:
        return []

    target_idx = week_dates.index(target_date)
    soup       = BeautifulSoup(html, "html.parser")
    locations  = []
    current_location = None

    for row in soup.select("tr"):
        cells = row.find_all(["td", "th"])

        if len(cells) >= 7:
            cell_text = cells[-7:][target_idx].get_text(separator=" ", strip=True)

            if current_location:
                time_ranges = re.findall(
                    r"\d+:\d+[ap]\s*-\s*\d+:\d+[ap]", cell_text, re.IGNORECASE
                )
                time_ranges = list(dict.fromkeys(time_ranges))
                closed = "closed" in cell_text.lower() or len(time_ranges) == 0

                locations.append({
                    "location": current_location,
                    "closed":   closed,
                    "hours":    time_ranges,
                })
                current_location = None

        elif len(cells) == 1:
            text = cells[0].get_text(strip=True).rstrip(">").strip()
            if text and len(text) > 3 and not re.match(r"^[\d\s]+$", text):
                current_location = text

    return locations


# ---------------------------------------------------------------------------
# Scrape with retries
# ---------------------------------------------------------------------------

def scrape_hours(target_date_str: str, max_retries: int = 3) -> list[dict]:
    from playwright.sync_api import sync_playwright

    for attempt in range(max_retries):
        print(f"\n--- Attempt {attempt + 1} of {max_retries} ---")
        proxy   = get_proxy()
        browser = None

        try:
            with sync_playwright() as p:
                browser, context = make_context(p, proxy)
                page = context.new_page()

                print(f"Loading {URL} via proxy {proxy['server']} ...")
                page.goto(URL, wait_until="networkidle", timeout=60000)
                time.sleep(3)

                title = page.title()
                print(f"Page title: '{title}'")

                # Check for Cloudflare block
                if any(x in title for x in ["Just a moment", "Cloudflare", "403", "Access Denied"]):
                    print("Blocked — trying next proxy...")
                    browser.close()
                    continue

                # Wait for the hours table to appear
                try:
                    page.wait_for_selector("tr", timeout=15000)
                except Exception:
                    print("Hours table not found — retrying...")
                    browser.close()
                    continue

                # Remove cookie banner if present
                page.evaluate("""
                    var banner = document.getElementById('onetrust-banner-sdk');
                    if (banner) banner.remove();
                """)

                # Click next week button
                print("Clicking next week...")
                clicked = False
                for selector in [
                    "button[aria-label*='Next']",
                    "button[aria-label*='next']",
                    "//button[contains(., '›')]",
                    "//button[contains(., '>')]",
                ]:
                    try:
                        if selector.startswith("//"):
                            btn = page.locator(f"xpath={selector}").last
                        else:
                            btn = page.locator(selector).last
                        btn.click(timeout=5000)
                        page.wait_for_load_state("networkidle", timeout=10000)
                        time.sleep(3)
                        clicked = True
                        print(f"Clicked: {selector}")
                        break
                    except Exception:
                        continue

                if not clicked:
                    print("Could not click next week — retrying...")
                    browser.close()
                    continue

                html       = page.content()
                week_dates = get_week_dates(html)
                print(f"Visible dates: {week_dates}")

                if target_date_str not in week_dates:
                    print("Target date not visible — retrying...")
                    browser.close()
                    continue

                locations = scrape_target_date(html, week_dates, target_date_str)
                browser.close()

                if locations:
                    print(f"Successfully scraped {len(locations)} locations.")
                    return locations
                else:
                    print("0 locations found — retrying...")

        except Exception as e:
            print(f"Error on attempt {attempt + 1}: {e}")
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            time.sleep(2)

    return []


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def handler(event, context):
    table_name  = os.environ.get("DYNAMODB_TABLE_NAME")
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    region      = os.environ.get("AWS_REGION", "us-east-2")

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table    = dynamodb.Table(table_name)
    s3       = boto3.client("s3", region_name=region)

    now     = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    central = timezone(timedelta(hours=-5))

    target_date_str = (now.astimezone(central) + timedelta(days=7)).strftime("%Y-%m-%d")
    print(f"Target date: {target_date_str}")

    locations_data = scrape_hours(target_date_str)

    if not locations_data:
        return {"statusCode": 500, "body": json.dumps({"error": "Failed to scrape hours."})}

    scraped_data = {
        "date":           target_date_str,
        "scraped_at":     now_iso,
        "source":         "dineoncampus.com/tamu/hours-of-operation",
        "location_count": len(locations_data),
        "locations":      locations_data,
    }

    s3_key = f"scrapes/hours/{target_date_str}/{now_iso}.json"
    s3.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=json.dumps(scraped_data, indent=2),
        ContentType="application/json",
    )
    print(f"Wrote to s3://{bucket_name}/{s3_key}")

    table.put_item(
        Item={
            "PK":             "SCRAPE_HOURS#latest",
            "SK":             f"SCRAPE_HOURS#{now_iso}",
            "scraped_at":     now_iso,
            "source":         "dineoncampus.com/tamu/hours-of-operation",
            "date":           target_date_str,
            "location_count": len(locations_data),
            "s3_key":         s3_key,
        }
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "scraped_at":   now_iso,
            "target_date":  target_date_str,
            "locations":    len(locations_data),
            "s3_key":       s3_key,
        }),
    }
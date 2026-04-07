"""
Lambda handler for scheduled TAMU dining HOURS scraping.
Triggered by EventBridge every day at 2:00am (configured in template.yaml).
Scrapes the hours for exactly 1 week (7 days) from the current execution date.

Dependencies (add to your Lambda layer or requirements.txt):
  - selenium
  - undetected-chromedriver
  - beautifulsoup4
  - boto3
"""

import os
import zipfile
import shutil

# MUST remain at the very top so undetected_chromedriver has a safe place to write patches
os.environ["HOME"] = "/tmp"
os.chdir("/tmp")

import json
import time
import re
import platform
from datetime import datetime, timezone, timedelta

import boto3
from bs4 import BeautifulSoup

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
URL = "https://dineoncampus.com/tamu/hours-of-operation"

# ---------------------------------------------------------------------------
# Selenium Helpers
# ---------------------------------------------------------------------------

def make_driver():
    from seleniumbase import Driver
    import shutil
    import os
    import random

    if os.path.exists("/tmp/chrome-user-data"):
        shutil.rmtree("/tmp/chrome-user-data")

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

    proxy_ip = random.choice(WEBSHARE_IPS)
    PROXY_STR = f"{WEBSHARE_CREDENTIALS}@{proxy_ip}"
    
    print(f"-> Setting up SeleniumBase with Webshare Proxy: {proxy_ip}...")

    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    driver = Driver(
        uc=True,            
        headless2=True,     
        no_sandbox=True,
        agent=user_agent,   
        proxy=PROXY_STR,
        binary_location="/usr/bin/google-chrome",
        user_data_dir="/tmp/chrome-user-data",
        chromium_arg="--disable-dev-shm-usage,--disable-gpu,--no-zygote,--disable-software-rasterizer"
    )
    return driver

def get_week_dates(driver) -> list[str]:
    """Extract the 7 dates (YYYY-MM-DD) for the currently displayed week."""
    soup = BeautifulSoup(driver.page_source, "html.parser")
    heading_el = soup.find(string=re.compile(r"Week of"))
    
    if not heading_el:
        today = datetime.now()
        sunday = today - timedelta(days=today.weekday() + 1) if today.weekday() != 6 else today
        return [(sunday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    text = heading_el.strip()
    m = re.search(r"Week of (\w+ \d+)\w*, (\d{4})", text)
    if m:
        date_str = f"{m.group(1)} {m.group(2)}"
        try:
            start = datetime.strptime(date_str, "%B %d %Y")
            return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        except ValueError:
            pass
            
    return []

def click_next_week(driver):
    print("Waiting for calendar elements to render...")
    
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "button"))
        )
        time.sleep(3)
    except Exception as e:
        print(f"Timeout waiting for page to render: {e}")

    try:
        driver.execute_script("""
            var banner = document.getElementById('onetrust-banner-sdk');
            if (banner) banner.remove();
        """)
    except:
        pass

    print("Attempting to advance calendar...")
    
    selectors = [
        "button[aria-label*='Next']",
        "button[aria-label*='next']",
        "button.direction-icon:last-of-type",
        "//button[contains(., '›')]",
        "//button[contains(., '>')]"
    ]

    for selector in selectors:
        try:
            if selector.startswith("//"):
                elements = driver.find_elements(By.XPATH, selector)
            else:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)

            if elements:
                btn = elements[-1]
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", btn)
                print(f"Clicked button using selector: {selector}")
                
                time.sleep(5) 
                return True
        except:
            continue

    return False

def scrape_target_date(driver, week_dates: list[str], target_date: str) -> list[dict]:
    """Scrape ONLY the column that matches the target_date."""
    if target_date not in week_dates:
        return []
        
    target_idx = week_dates.index(target_date)
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

    locations = []
    current_location = None

    rows = soup.select("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        
        if len(cells) >= 7:
            hours_cells = cells[-7:]
            target_cell = hours_cells[target_idx]
            cell_text = target_cell.get_text(separator=" ", strip=True)
            
            if current_location:
                time_ranges = re.findall(r"\d+:\d+[ap]\s*-\s*\d+:\d+[ap]", cell_text, re.IGNORECASE)
                time_ranges = list(dict.fromkeys(time_ranges))
                
                closed = "Closed" in cell_text or "closed" in cell_text.lower() or len(time_ranges) == 0
                
                locations.append({
                    "location": current_location,
                    "closed": closed,
                    "hours": time_ranges
                })
                current_location = None

        elif len(cells) == 1:
            text = cells[0].get_text(strip=True).rstrip(">").strip()
            if text and len(text) > 3 and not re.match(r"^[\d\s]+$", text):
                current_location = text

    return locations

# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def handler(event, context):
    table_name = os.environ.get("DYNAMODB_TABLE_NAME")
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    region = os.environ.get("AWS_REGION", "us-east-2")

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)
    s3 = boto3.client("s3", region_name=region)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    central = timezone(timedelta(hours=-5))
    
    target_datetime = now.astimezone(central) + timedelta(days=7)
    target_date_str = target_datetime.strftime("%Y-%m-%d")

    print(f"Target Date to scrape: {target_date_str}")

    # ---- 1. Scrape the data with Retries ----------------------------------
    max_retries = 3
    locations_data = []

    for attempt in range(max_retries):
        print(f"\n--- Attempt {attempt + 1} of {max_retries} ---")
        driver = None
        try:
            driver = make_driver()
            driver.set_page_load_timeout(90)
            
            print(f"Loading {URL} ...")
            driver.uc_open_with_reconnect(URL, reconnect_time=10)
            time.sleep(5) 
            
            title = driver.title
            print(f"Current Page Title: '{title}'")
            
            # Check for Cloudflare / Proxy failure
            if not title or "Just a moment" in title or "Cloudflare" in title or "403" in title or "Access Denied" in title:
                print("Cloudflare or bad proxy detected. Attempting auto-bypass...")
                try:
                    driver.uc_gui_click_captcha()
                    time.sleep(10)
                    title = driver.title
                except:
                    pass
                
                # If still blocked after bypass attempt
                if not title or "Just a moment" in title or "Cloudflare" in title or "403" in title:
                    print("Bypass failed or proxy is dead. Tearing down and retrying...")
                    driver.quit()
                    time.sleep(2)
                    continue
            
            # If we survived Cloudflare, advance the calendar
            print("Successfully connected. Advancing to next week...")
            if not click_next_week(driver):
                print("Failed to click 'Next' button. Retrying...")
                driver.quit()
                continue
                
            # Scrape the actual dates
            week_dates = get_week_dates(driver)
            print(f"Visible dates: {week_dates}")
            
            if target_date_str not in week_dates:
                print("Target date is not visible on the calendar. Retrying...")
                driver.quit()
                continue

            # Extract the hours data
            locations_data = scrape_target_date(driver, week_dates, target_date_str)
            
            if locations_data:
                print(f"Successfully scraped {len(locations_data)} locations!")
                driver.quit()
                break # Success! Break the loop
            else:
                print("Scraping returned 0 locations. Retrying...")
                driver.quit()

        except Exception as e:
            print(f"⚠️ Error during attempt {attempt + 1}: {e}")
            if driver:
                try:
                    print(f"Visible text snippet: {driver.get_text('body')[:150]}")
                except:
                    pass
                driver.quit()
            time.sleep(2)

    # ---- 2. Handle complete failure ---------------------------------------
    if not locations_data:
        print("[Error] Failed to scrape hours after all retries.")
        return {"statusCode": 500, "body": json.dumps({"error": "Failed to extract locations for target date."})}

    # ---- 3. Build final payload -------------------------------------------
    scraped_data = {
        "date": target_date_str,
        "scraped_at": now_iso,
        "source": "dineoncampus.com/tamu/hours-of-operation",
        "location_count": len(locations_data),
        "locations": locations_data
    }

    # ---- 4. Write full JSON blob to S3 ------------------------------------
    s3_key = f"scrapes/hours/{target_date_str}/{now_iso}.json"
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
            "scraped_at":     now_iso,
            "target_date":    target_date_str,
            "locations":      len(locations_data),
            "s3_key":         s3_key
        }),
    }
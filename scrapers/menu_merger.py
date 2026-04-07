import os
import json
import boto3
from datetime import datetime, timezone, timedelta

def handler(event, context):
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    table_name = os.environ.get("DYNAMODB_TABLE_NAME")
    region = os.environ.get("AWS_REGION", "us-east-2")

    s3 = boto3.client("s3", region_name=region)
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    # 1. Figure out "Today's" date in Central Time
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    central = timezone(timedelta(hours=-5)) # CST/CDT
    today = now.astimezone(central).strftime("%Y-%m-%d")

    prefix = f"scrapes/menu/{today}/"
    print(f"Looking for files in s3://{bucket_name}/{prefix}...")

    # 2. Get all JSON files from today
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    
    # Filter out any old master files just in case this runs twice
    files = [
        obj['Key'] for obj in response.get('Contents', []) 
        if obj['Key'].endswith('.json') and "merged" not in obj['Key']
    ]

    if not files:
        print("No fragmented scrapes found for today. Exiting.")
        return {"statusCode": 200, "body": "No files to merge."}

    print(f"Found {len(files)} partial scrapes. Merging...")

    master_menus = {}
    skipped_closed_total = 0

    # 3. Read and merge the data
    for file_key in files:
        obj = s3.get_object(Bucket=bucket_name, Key=file_key)
        data = json.loads(obj['Body'].read().decode('utf-8'))
        
        # Keep a running tally of skipped/closed locations for the DB stats
        skipped_closed_total += data.get('skipped_closed', 0)
        
        for menu in data.get('menus', []):
            unique_id = f"{menu['location_id']}_{menu['period_name']}"
            if unique_id not in master_menus:
                master_menus[unique_id] = menu

    # 4. Calculate final accurate statistics
    merged_menu_list = list(master_menus.values())
    total_items = sum(menu.get('item_count', 0) for menu in merged_menu_list)
    unique_locations = len(set(menu['location_id'] for menu in merged_menu_list))

    final_output = {
        "scraped_at": now_iso,
        "source": "dineoncampus.com/tamu (Merged)",
        "date": today,
        "location_count": unique_locations,
        "total_menu_entries": len(merged_menu_list),
        "total_items": total_items,
        "skipped_closed": skipped_closed_total,
        "menus": merged_menu_list
    }

    # 5. Save the Merged Master File back to S3
    merged_s3_key = f"scrapes/menu/{today}/merged_master_{now_iso}.json"
    s3.put_object(
        Bucket=bucket_name,
        Key=merged_s3_key,
        Body=json.dumps(final_output, indent=2),
        ContentType="application/json"
    )
    print(f"Saved merged file to: {merged_s3_key}")

    # 6. Update DynamoDB to point the Frontend to the new Master File
    table.put_item(
        Item={
            "PK": "SCRAPE#latest",
            "SK": f"SCRAPE#MERGED#{now_iso}",
            "scraped_at": now_iso,
            "source": "dineoncampus.com/tamu (Merged)",
            "date": today,
            "location_count": unique_locations,
            "total_menu_entries": len(merged_menu_list),
            "total_items": total_items,
            "s3_key": merged_s3_key,
        }
    )
    print("DynamoDB SCRAPE#latest successfully updated!")

    # 7. Clean up: Delete the original fragmented files
    if files:
        # Boto3 requires the delete list to be formatted as a list of dicts
        objects_to_delete = [{'Key': file_key} for file_key in files]
        
        s3.delete_objects(
            Bucket=bucket_name,
            Delete={'Objects': objects_to_delete}
        )
        print(f"Cleaned up {len(files)} fragmented files from S3.")
    # -------------------------

    return {"statusCode": 200, "body": f"Successfully merged and cleaned {len(files)} files."}
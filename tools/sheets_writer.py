#!/usr/bin/env python3
import argparse
import json
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",  # optional but helpful
]

ILLEGAL_TITLE_CHARS = r'[\[\]\:\*\?\/\\]'
TITLE_MAX_LEN = 100

def sanitize_sheet_title(raw: str) -> str:
    """Sheets tab titles cannot contain []:*?/\\ and must be <= 100 chars."""
    title = re.sub(ILLEGAL_TITLE_CHARS, "_", raw)
    # Strip leading/trailing whitespace and limit length
    title = title.strip()[:TITLE_MAX_LEN]
    # Avoid empty titles
    return title or "untitled"

def a1_escape(title: str) -> str:
    """Escape sheet title for A1 notation: wrap in single quotes and double any single quotes."""
    return f"'{title.replace(\"'\", \"''\")}'"

def ensure_sheet_and_get_id(svc, spreadsheet_id: str, title: str) -> int:
    """Return sheetId for title; create if missing."""
    ss = svc.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets(properties(sheetId,title))").execute()
    sheets = ss.get("sheets", [])
    for s in sheets:
        props = s.get("properties", {})
        if props.get("title") == title:
            return int(props["sheetId"])

    # Create the sheet
    req = {
        "requests": [
            {"addSheet": {"properties": {"title": title}}}
        ]
    }
    resp = svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=req).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    return int(sheet_id)

def prepend_row(svc, spreadsheet_id: str, sheet_id: int, title: str, timestamp_ist: str, json_blob: str):
    """
    Insert a new first row, then write [timestamp, json_blob] into A1:B1.
    Two-step approach: insertDimension + values.update.
    """
    # 1) Insert row at index 0
    insert_req = {
        "requests": [
            {
                "insertDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": 1
                    },
                    "inheritFromBefore": False
                }
            }
        ]
    }
    svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=insert_req).execute()

    # 2) Write values into the new top row
    range_a1 = f"{a1_escape(title)}!A1:B1"
    body = {"values": [[timestamp_ist, json_blob]]}
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueInputOption="RAW",
        body=body
    ).execute()

def write_with_retry(svc, spreadsheet_id: str, sheet_id: int, title: str, timestamp_ist: str, json_blob: str):
    try:
        prepend_row(svc, spreadsheet_id, sheet_id, title, timestamp_ist, json_blob)
    except HttpError as e:
        # retry once after a short backoff
        time.sleep(2.0)
        prepend_row(svc, spreadsheet_id, sheet_id, title, timestamp_ist, json_blob)

def main():
    parser = argparse.ArgumentParser(description="Write script JSON outputs to Google Sheets, prepending a row per script.")
    parser.add_argument("--service-account-json", required=True, help="Path to service account JSON key.")
    parser.add_argument("--spreadsheet-id", required=True, help="Target Google Spreadsheet ID.")
    parser.add_argument("--results-file", required=True, help="Path to results.jsonl (one JSON per line: {name, json}).")
    args = parser.parse_args()

    # Load results lines (may be empty)
    results = []
    try:
        with open(args.results_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    # Expected fields: name, json
                    results.append(obj)
                except json.JSONDecodeError:
                    # Skip malformed line
                    continue
    except FileNotFoundError:
        # Nothing to write
        results = []

    if not results:
        print("No successful script outputs to write.", file=sys.stderr)
        return 0

    # Auth
    creds = Credentials.from_service_account_file(args.service_account_json, scopes=SCOPES)
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Current timestamp in IST
    ts = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()

    # For each result, ensure sheet exists and prepend row
    for item in results:
        raw_title = str(item.get("name", "")).strip()
        raw_json = str(item.get("json", ""))

        title = sanitize_sheet_title(raw_title)
        try:
            sheet_id = ensure_sheet_and_get_id(svc, args.spreadsheet_id, title)
            write_with_retry(svc, args.spreadsheet_id, sheet_id, title, ts, raw_json)
            print(f"Wrote top row to sheet '{title}'")
        except Exception as e:
            # Skip on repeated failure per your policy
            print(f"Skipped '{title}' due to error: {e}", file=sys.stderr)
            continue

    return 0

if __name__ == "__main__":
    sys.exit(main())

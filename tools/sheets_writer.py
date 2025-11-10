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
    "https://www.googleapis.com/auth/drive.file",
]

ILLEGAL_TITLE_CHARS = r'[\[\]\:\*\?\/\\]'
TITLE_MAX_LEN = 100


def sanitize_sheet_title(raw: str) -> str:
    """Sheets tab names cannot contain []:*?/\\ and must be <= 100 chars."""
    title = re.sub(ILLEGAL_TITLE_CHARS, "_", raw)
    title = title.strip()[:TITLE_MAX_LEN]
    return title or "untitled"


def a1_escape(title: str) -> str:
    """
    Escape sheet titles for A1 notation:
    Wrap in single quotes and double any internal single quotes.
    No f-strings used to avoid escaping confusion.
    """
    title = title.replace("'", "''")
    return "'" + title + "'"


def ensure_sheet_and_get_id(svc, spreadsheet_id: str, title: str) -> int:
    """Return sheetId for title; create if not present."""
    ss = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title))"
    ).execute()

    for s in ss.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == title:
            return int(props["sheetId"])

    req = {
        "requests": [
            {"addSheet": {"properties": {"title": title}}}
        ]
    }
    resp = svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body=req
    ).execute()

    return int(resp["replies"][0]["addSheet"]["properties"]["sheetId"])


def prepend_row(svc, spreadsheet_id: str, sheet_id: int, title: str, timestamp_ist: str, json_blob: str):
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
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body=insert_req
    ).execute()

    range_a1 = a1_escape(title) + "!A1:B1"
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
    except HttpError:
        time.sleep(2.0)
        prepend_row(svc, spreadsheet_id, sheet_id, title, timestamp_ist, json_blob)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-account-json", required=True)
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--results-file", required=True)
    args = parser.parse_args()

    results = []
    try:
        with open(args.results_file, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    results.append(json.loads(line))
                except:
                    pass
    except:
        pass

    if not results:
        print("No successful outputs to write.", file=sys.stderr)
        return 0

    creds = Credentials.from_service_account_file(args.service_account_json, scopes=SCOPES)
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    timestamp_ist = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()

    for item in results:
        title = sanitize_sheet_title(str(item.get("name", "")).strip())
        raw_json = str(item.get("json", ""))
        try:
            sheet_id = ensure_sheet_and_get_id(svc, args.spreadsheet_id, title)
            write_with_retry(svc, args.spreadsheet_id, sheet_id, title, timestamp_ist, raw_json)
            print(f"✔ Wrote → {title}")
        except Exception as e:
            print(f"✖ Skipped {title}: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

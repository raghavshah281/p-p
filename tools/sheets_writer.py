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
    """Escape tab names for A1 notation: wrap in single quotes and double internal single quotes."""
    title = title.replace("'", "''")
    return "'" + title + "'"


def ensure_sheet_and_get_id(svc, spreadsheet_id: str, title: str) -> int:
    """Return sheetId for title; create if missing."""
    ss = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title))"
    ).execute()

    for s in ss.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == title:
            return int(props["sheetId"])

    req = {"requests": [{"addSheet": {"properties": {"title": title}}}]}
    resp = svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=req).execute()
    return int(resp["replies"][0]["addSheet"]["properties"]["sheetId"])


def prepend_row(svc, spreadsheet_id: str, sheet_id: int, title: str, timestamp_ist: str, json_blob: str):
    """Insert a new top row and write [timestamp, json_blob] to A1:B1."""
    insert_req = {
        "requests": [
            {
                "insertDimension": {
                    "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                    "inheritFromBefore": False,
                }
            }
        ]
    }
    svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=insert_req).execute()

    range_a1 = f"{a1_escape(title)}!A1:B1"
    body = {"values": [[timestamp_ist, json_blob]]}
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=range_a1, valueInputOption="RAW", body=body
    ).execute()


def write_with_retry(svc, spreadsheet_id: str, sheet_id: int, title: str, timestamp_ist: str, json_blob: str):
    try:
        prepend_row(svc, spreadsheet_id, sheet_id, title, timestamp_ist, json_blob)
    except HttpError:
        time.sleep(2.0)
        prepend_row(svc, spreadsheet_id, sheet_id, title, timestamp_ist, json_blob)


def load_results_jsonl(path: str):
    """
    Load results that should be JSONL. Tolerant to:
    - pretty-printed objects (multi-line)
    - stray masked lines like "***" (GitHub log masking in previews)
    """
    results = []
    with open(path, "r", encoding="utf-8") as fh:
        lines = [ln.rstrip("\n\r") for ln in fh]

    # Fast path: JSONL one object per line
    for ln in lines:
        if not ln or ln == "***":
            continue
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict) and "name" in obj and "json" in obj:
                results.append(obj)
        except json.JSONDecodeError:
            pass

    if results:
        return results

    # Slow path: try to stitch multi-line objects between balanced braces
    buf = []
    depth = 0
    for ln in lines:
        if ln == "***" or not ln.strip():
            continue
        # crude balance counter
        depth += ln.count("{") - ln.count("}")
        buf.append(ln)
        if depth <= 0 and buf:
            chunk = "\n".join(buf)
            try:
                obj = json.loads(chunk)
                if isinstance(obj, dict) and "name" in obj and "json" in obj:
                    results.append(obj)
            except json.JSONDecodeError:
                pass
            buf = []
            depth = 0
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-account-json", required=True)
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--results-file", required=True)
    args = parser.parse_args()

    try:
        results = load_results_jsonl(args.results_file)
    except FileNotFoundError:
        results = []

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

    return 0


if __name__ == "__main__":
    sys.exit(main())

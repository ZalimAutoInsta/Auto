"""
Daily Post Draft Bot
---------------------
Reads the next "pending" idea from a Google Sheet and sends it to a
personal Telegram chat as a draft, with an inline "Approve" button.

Run via GitHub Actions on a daily schedule. See README for setup.
"""

import os
import sys
import json
import requests
import gspread
from google.oauth2.service_account import Credentials

# ---------------------------------------------------------------------------
# Configuration (pulled from environment variables / GitHub Secrets)
# ---------------------------------------------------------------------------
GOOGLE_CREDS_JSON = os.environ["GOOGLE_CREDS_JSON"]       # full JSON key, as a string
SHEET_ID = os.environ["SHEET_ID"]                          # Google Sheet ID
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "Sheet1")
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

IDEA_COLUMN = "Idea"
STATUS_COLUMN = "Status"
PENDING_VALUE = "pending"
SENT_VALUE = "sent"  # marks "draft was sent to Telegram", not "approved"


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------
def get_worksheet():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    return sheet.worksheet(WORKSHEET_NAME)


def get_next_pending_row(worksheet):
    """Return (row_number, idea_text) for the first row with Status == pending."""
    records = worksheet.get_all_records()  # list of dicts, keyed by header row
    headers = worksheet.row_values(1)

    if IDEA_COLUMN not in headers or STATUS_COLUMN not in headers:
        raise ValueError(
            f"Sheet must have '{IDEA_COLUMN}' and '{STATUS_COLUMN}' columns. "
            f"Found: {headers}"
        )

    for i, record in enumerate(records, start=2):  # row 1 = headers
        status = str(record.get(STATUS_COLUMN, "")).strip().lower()
        if status == PENDING_VALUE or status == "":
            idea = record.get(IDEA_COLUMN, "").strip()
            if idea:
                return i, idea
    return None, None


def mark_row_sent(worksheet, row_number):
    headers = worksheet.row_values(1)
    status_col_index = headers.index(STATUS_COLUMN) + 1  # 1-indexed
    worksheet.update_cell(row_number, status_col_index, SENT_VALUE)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def send_telegram_draft(idea_text, row_number):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    message = f"📝 *Today's Post Draft*\n\n{idea_text}"

    # Inline keyboard with Approve / Reject buttons.
    # callback_data encodes the row number so a future webhook/poller
    # can know which row to update.
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"approve:{row_number}"},
                {"text": "❌ Reject", "callback_data": f"reject:{row_number}"},
            ]
        ]
    }

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard),
    }

    response = requests.post(url, data=payload, timeout=15)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    worksheet = get_worksheet()
    row_number, idea = get_next_pending_row(worksheet)

    if row_number is None:
        print("No pending ideas found in the sheet. Nothing to send.")
        sys.exit(0)

    print(f"Sending row {row_number}: {idea[:60]}...")
    send_telegram_draft(idea, row_number)
    mark_row_sent(worksheet, row_number)
    print("Done. Row marked as sent.")


if __name__ == "__main__":
    main()

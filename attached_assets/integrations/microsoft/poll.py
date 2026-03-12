#!/usr/bin/env python3
"""
Microsoft Graph API email poller for OpenClaw.
- Polls Inbox and Sent Items
- Tracks per-contact state in last-seen-emails.md
- Shorter poll interval for known contacts (2 min vs 5 min)
- Writes to OUTLOOK_INBOX.md (sent items prefixed with [SENT])
- Triggers immediate alert file when new email from known contact arrives
"""
import json
import os
import re
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR        = Path.home() / ".openclaw"
TOKEN_FILE       = STATE_DIR / "integrations/microsoft/token.json"
INBOX_MD         = STATE_DIR / "workspace/OUTLOOK_INBOX.md"
LAST_SEEN_FILE   = STATE_DIR / "workspace/memory/last-seen-emails.md"
ALERT_FILE       = STATE_DIR / "workspace/memory/email-alert.md"
LOG_FILE         = STATE_DIR / "workspace/memory/poll-log.txt"

POLL_INTERVAL_KNOWN    = 120   # seconds between polls for known contacts
POLL_INTERVAL_GENERAL  = 300   # seconds between general inbox polls
MAX_RESULTS            = 25

KNOWN_CONTACTS = [
    "stuart.hobin@croydemedical.co.uk",
    "emily.thomas@croydemedical.co.uk",
    "john@reveela.com",
    "ed.patchett@7thsense.one",
    "johnjamesmarsh@hotmail.com",
    "andy.barrett@sjpp.co.uk",
    "olivia.collington@collingtonwinter.co.uk",
]

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)
    print(line, end="")


def load_token() -> dict:
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(f"Token file not found: {TOKEN_FILE}\nRun the Microsoft auth flow first.")
    with open(TOKEN_FILE) as f:
        return json.load(f)


def refresh_access_token(token_data: dict) -> str:
    """Refresh OAuth token using refresh_token grant."""
    resp = requests.post(
        f"https://login.microsoftonline.com/{token_data['tenant_id']}/oauth2/v2.0/token",
        data={
            "client_id":     token_data["client_id"],
            "client_secret": token_data.get("client_secret", ""),
            "refresh_token": token_data["refresh_token"],
            "grant_type":    "refresh_token",
            "scope":         "Mail.Read offline_access",
        },
        timeout=15,
    )
    resp.raise_for_status()
    new_data = resp.json()
    token_data["access_token"]  = new_data["access_token"]
    token_data["refresh_token"] = new_data.get("refresh_token", token_data["refresh_token"])
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)
    return token_data["access_token"]


def get_headers(token_data: dict) -> dict:
    return {"Authorization": f"Bearer {token_data['access_token']}", "Content-Type": "application/json"}


def fetch_emails(access_token: str, folder: str = "inbox", top: int = MAX_RESULTS) -> list:
    url = f"{GRAPH_BASE}/me/mailFolders/{folder}/messages"
    params = {
        "$top": top,
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,isRead",
    }
    resp = requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("value", [])


def load_last_seen() -> dict:
    """Returns dict of email -> ISO timestamp string (or empty string)."""
    state = {}
    if not LAST_SEEN_FILE.exists():
        return state
    for line in LAST_SEEN_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 1)
        if len(parts) == 2:
            email = parts[0].strip().lower()
            ts    = parts[1].strip()
            state[email] = ts
    return state


def save_last_seen(state: dict):
    LAST_SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Last Seen Emails — Known Contacts\n",
             "# Format: contact-email | last-seen-timestamp (ISO 8601)\n"]
    for email, ts in sorted(state.items()):
        lines.append(f"{email} | {ts}\n")
    LAST_SEEN_FILE.write_text("".join(lines))


def format_md_entry(msg: dict, prefix: str = "") -> str:
    received  = msg.get("receivedDateTime", "")
    subject   = msg.get("subject", "(no subject)")
    sender    = msg.get("from", {}).get("emailAddress", {})
    from_name = sender.get("name", "")
    from_addr = sender.get("address", "")
    preview   = msg.get("bodyPreview", "").replace("\r\n", " ").replace("\n", " ")[:300]
    ts_fmt    = received[:16].replace("T", " ") if received else "unknown"
    tag       = f"[{prefix}] " if prefix else ""
    return (
        f"---\n"
        f"{tag}**{subject}**\n"
        f"From: {from_name} <{from_addr}> | {ts_fmt}\n"
        f"{preview}\n\n"
    )


def write_alert(subject: str, from_addr: str, from_name: str, received: str, direction: str):
    ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ALERT_FILE, "a") as f:
        f.write(
            f"[{ts}] NEW {direction} from known contact:\n"
            f"  From: {from_name} <{from_addr}>\n"
            f"  Subject: {subject}\n"
            f"  Received: {received[:16]}\n\n"
        )
    log(f"ALERT: New {direction} from {from_addr} — {subject}")


def process_emails(emails: list, last_seen: dict, direction: str = "INBOX") -> tuple[list, bool]:
    """Returns (new_entries_md, any_known_contact_alert)."""
    new_entries  = []
    known_alert  = False

    for msg in emails:
        received  = msg.get("receivedDateTime", "")
        sender    = msg.get("from", {}).get("emailAddress", {})
        from_addr = sender.get("address", "").lower()
        from_name = sender.get("name", from_addr)
        subject   = msg.get("subject", "(no subject)")

        if from_addr in [c.lower() for c in KNOWN_CONTACTS]:
            prev_ts = last_seen.get(from_addr, "")
            if received > prev_ts:
                last_seen[from_addr] = received
                write_alert(subject, from_addr, from_name, received, direction)
                known_alert = True
                new_entries.append(format_md_entry(msg, prefix="SENT" if direction == "SENT" else ""))
        else:
            new_entries.append(format_md_entry(msg, prefix="SENT" if direction == "SENT" else ""))

    return new_entries, known_alert


def rebuild_inbox_md(inbox_entries: list, sent_entries: list):
    INBOX_MD.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"# Outlook — Inbox & Sent Items\n_Last updated: {ts}_\n\n"
    content += "## Inbox\n\n" + "".join(inbox_entries) if inbox_entries else "## Inbox\n\n_(empty)_\n\n"
    content += "\n## Sent Items\n\n" + "".join(sent_entries) if sent_entries else "\n## Sent Items\n\n_(empty)_\n\n"
    INBOX_MD.write_text(content)


def main():
    log("Microsoft email poller starting")
    last_known_poll   = 0.0
    last_general_poll = 0.0

    while True:
        now = time.time()
        run_known_check   = (now - last_known_poll)   >= POLL_INTERVAL_KNOWN
        run_general_check = (now - last_general_poll) >= POLL_INTERVAL_GENERAL

        if run_known_check or run_general_check:
            try:
                token_data    = load_token()
                access_token  = refresh_access_token(token_data)
                last_seen     = load_last_seen()

                inbox_emails  = fetch_emails(access_token, folder="inbox")
                sent_emails   = fetch_emails(access_token, folder="sentitems")

                inbox_entries, _ = process_emails(inbox_emails, last_seen, direction="INBOX")
                sent_entries,  _ = process_emails(sent_emails,  last_seen, direction="SENT")

                save_last_seen(last_seen)
                rebuild_inbox_md(inbox_entries, sent_entries)

                last_known_poll   = now
                last_general_poll = now
                log(f"Poll complete — {len(inbox_entries)} inbox, {len(sent_entries)} sent")

            except Exception as e:
                log(f"Poll error: {e}")

        time.sleep(30)


if __name__ == "__main__":
    main()

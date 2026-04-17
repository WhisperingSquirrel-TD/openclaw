#!/usr/bin/env python3
"""
Google Calendar poller for OpenClaw.
- Fetches events for the next 14 days from Google Calendar API
- Writes output to GOOGLE_CALENDAR.md in the workspace/memory directory
- Runs continuously, polling every 15 minutes

Auth files (already on Pi from previous setup):
  ~/.openclaw/integrations/google/credentials.json   — OAuth app credentials
  ~/.openclaw/integrations/google/token.json         — saved OAuth token (auto-refreshed)

First-run (if token.json is missing or expired):
  python3 ~/.openclaw/integrations/google/poll-calendar-google.py
  It will open a browser for OAuth consent and save the token automatically.

Requires:
  pip3 install --break-system-packages google-auth google-auth-oauthlib google-api-python-client
"""

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    raise SystemExit(
        "Missing Google libraries.\n"
        "Run: pip3 install --break-system-packages google-auth google-auth-oauthlib google-api-python-client"
    )

STATE_DIR   = Path.home() / ".openclaw"
CALENDAR_MD = STATE_DIR / "workspace/GOOGLE_CALENDAR.md"
LOG_FILE    = STATE_DIR / "workspace/memory/poll-calendar-google-log.txt"

# Credentials: try the calendar-specific file first, fall back to the shared
# gmail-credentials.json that the Gmail poller also uses — both use the same
# OAuth app so a single credentials.json file covers both.
_GOOGLE_DIR = STATE_DIR / "integrations/google"
CREDENTIALS_FILE = next(
    (p for p in [
        _GOOGLE_DIR / "credentials.json",
        _GOOGLE_DIR / "gmail-credentials.json",
    ] if p.exists()),
    _GOOGLE_DIR / "credentials.json",   # fallback (will error with clear message)
)

# Token: calendar uses its own token file (separate scope from Gmail)
TOKEN_FILE = _GOOGLE_DIR / "token.json"

SCOPES        = ["https://www.googleapis.com/auth/calendar.readonly"]
POLL_INTERVAL = 900   # 15 minutes
LOOK_AHEAD    = 14    # days

LOG_MAX_LINES = 1000
LOG_TRIM_TO   = 800


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [gcal-poller] {msg}\n"
    try:
        existing = LOG_FILE.read_text().splitlines(keepends=True)
    except FileNotFoundError:
        existing = []
    if len(existing) >= LOG_MAX_LINES:
        existing = existing[-LOG_TRIM_TO:]
    existing.append(line)
    tmp = LOG_FILE.with_suffix(".tmp")
    try:
        tmp.write_text("".join(existing))
        tmp.replace(LOG_FILE)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
    print(line, end="")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_service():
    log(f"Using credentials file: {CREDENTIALS_FILE}")
    log(f"Using token file:       {TOKEN_FILE}")

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            log(f"WARNING: Could not read token file: {e} — will attempt re-auth")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                TOKEN_FILE.write_text(creds.to_json())
                log("Token refreshed successfully")
            except Exception as e:
                log(f"ERROR: Token refresh failed: {e}")
                if "invalid_grant" in str(e).lower():
                    log("FLAG TO TOM: Google Calendar token revoked (invalid_grant).")
                    log(f"  Delete {TOKEN_FILE} and re-run manually to re-authenticate:")
                    log(f"  python3 {__file__}")
                return None
        else:
            if not CREDENTIALS_FILE.exists():
                log(f"ERROR: Google credentials file not found.")
                log(f"  Checked: ~/.openclaw/integrations/google/credentials.json")
                log(f"  Checked: ~/.openclaw/integrations/google/gmail-credentials.json")
                log("  Download OAuth credentials from Google Cloud Console → APIs & Services → Credentials")
                log("  Save as ~/.openclaw/integrations/google/credentials.json")
                return None
            try:
                log("Starting OAuth flow — attempting local server (needs browser access to Pi)")
                log("If this hangs, run on a machine with a browser, then copy token.json to the Pi")
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
                creds = flow.run_local_server(port=0)
                TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_FILE.write_text(creds.to_json())
                log(f"OAuth consent complete — token saved to {TOKEN_FILE}")
            except Exception as e:
                log(f"ERROR: OAuth flow failed: {e}")
                log("FLAG TO TOM: Google Calendar OAuth could not complete automatically.")
                log("  Run on a machine with a browser:")
                log(f"    python3 {__file__}")
                log("  Then copy the token.json file to the Pi:")
                log(f"    scp ~/.openclaw/integrations/google/token.json pi@<pi-ip>:{TOKEN_FILE}")
                return None

    try:
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        log(f"ERROR: Failed to build calendar service: {e}")
        return None


# ---------------------------------------------------------------------------
# Fetch events
# ---------------------------------------------------------------------------

def fetch_events(service) -> list:
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=LOOK_AHEAD)).isoformat()

    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=100,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return result.get("items", [])
    except Exception as e:
        log(f"ERROR: Calendar fetch failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Format events
# ---------------------------------------------------------------------------

def fmt_dt(dt_obj: dict) -> str:
    if "dateTime" in dt_obj:
        raw = dt_obj["dateTime"]
        try:
            dt = datetime.fromisoformat(raw)
            return dt.strftime("%a %d %b %Y %H:%M")
        except Exception:
            return raw
    elif "date" in dt_obj:
        raw = dt_obj["date"]
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
            return dt.strftime("%a %d %b %Y (all day)")
        except Exception:
            return raw
    return "?"


def is_all_day(dt_obj: dict) -> bool:
    return "date" in dt_obj and "dateTime" not in dt_obj


def format_event(evt: dict) -> str:
    summary  = evt.get("summary", "(No title)")
    start    = fmt_dt(evt.get("start", {}))
    end      = fmt_dt(evt.get("end", {}))
    location = evt.get("location", "")
    attendees = evt.get("attendees", [])
    status   = evt.get("status", "")
    desc     = evt.get("description", "")

    attendee_names = []
    for a in attendees:
        name = a.get("displayName") or a.get("email", "")
        rsvp = a.get("responseStatus", "")
        if rsvp == "declined":
            name += " (declined)"
        elif rsvp == "tentative":
            name += " (tentative)"
        attendee_names.append(name)

    lines = [f"- **{summary}**"]
    if is_all_day(evt.get("start", {})):
        lines.append(f"  {start}")
    else:
        lines.append(f"  {start} → {end}")
    if location:
        lines.append(f"  📍 {location}")
    if attendee_names:
        lines.append(f"  👥 {', '.join(attendee_names)}")
    if desc:
        short_desc = desc.strip().replace("\n", " ")[:120]
        if len(desc.strip()) > 120:
            short_desc += "…"
        lines.append(f"  📝 {short_desc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Group by date and write markdown
# ---------------------------------------------------------------------------

def write_calendar_md(events: list):
    CALENDAR_MD.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Group events by date
    by_date: dict[str, list] = {}
    for evt in events:
        start = evt.get("start", {})
        if "dateTime" in start:
            day = datetime.fromisoformat(start["dateTime"]).strftime("%Y-%m-%d")
        elif "date" in start:
            day = start["date"]
        else:
            continue
        by_date.setdefault(day, []).append(evt)

    lines = [
        f"# Google Calendar (Next {LOOK_AHEAD} Days)\n",
        f"Last updated: {ts}\n\n",
    ]

    if not by_date:
        lines.append("_No events in the next 14 days._\n")
    else:
        for day in sorted(by_date.keys()):
            try:
                day_label = datetime.strptime(day, "%Y-%m-%d").strftime("%A %d %B %Y")
            except Exception:
                day_label = day
            lines.append(f"## {day_label}\n\n")
            for evt in by_date[day]:
                try:
                    lines.append(format_event(evt) + "\n\n")
                except Exception as e:
                    log(f"WARNING: Skipping malformed event: {e}")

    tmp = CALENDAR_MD.with_suffix(".tmp")
    try:
        tmp.write_text("".join(lines))
        tmp.replace(CALENDAR_MD)
        log(f"GOOGLE_CALENDAR.md updated — {len(events)} events over {len(by_date)} days")
    except Exception as e:
        log(f"ERROR: Could not write GOOGLE_CALENDAR.md: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def poll_once():
    service = get_service()
    if service is None:
        log("ERROR: Could not connect to Google Calendar — skipping this cycle")
        return
    events = fetch_events(service)
    write_calendar_md(events)


def main():
    log("Google Calendar poller started")
    while True:
        try:
            poll_once()
        except Exception as e:
            log(f"ERROR: Unhandled exception in poll cycle: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

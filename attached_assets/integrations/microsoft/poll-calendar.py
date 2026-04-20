#!/usr/bin/env python3
"""
Microsoft Graph API calendar poller for OpenClaw.
- Fetches calendar events for the next 14 days from Microsoft Graph
- Writes output to OUTLOOK_CALENDAR.md in the workspace
- Polls every 15 minutes

Usage:
  poll-calendar.py                          # uses token-assistant.json (default)
  poll-calendar.py --account microsoft      # uses token-microsoft.json (personal)
  poll-calendar.py --token-file /path/to/token.json
"""
import argparse
import json
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

STATE_DIR   = Path.home() / ".openclaw"
CALENDAR_MD = STATE_DIR / "workspace/OUTLOOK_CALENDAR.md"
LOG_FILE    = STATE_DIR / "workspace/memory/poll-calendar-log.txt"
GRAPH_BASE  = "https://graph.microsoft.com/v1.0"

# TOKEN_FILE is resolved at startup from --account / --token-file args (see main())
TOKEN_FILE: Path = None  # type: ignore[assignment]


def _resolve_token_file(account: str, explicit: str | None) -> Path:
    """Return the token file path for the given account slug.

    Resolution order (mirrors send.py / create-event.py):
      1. --token-file explicit path
      2. token-{account}.json in any microsoft* subdir
      3. token-assistant.json  (canonical assistant@ path)
      4. token-microsoft.json  (canonical personal path)
      5. token.json
    """
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"Explicit token file not found: {p}")
        return p

    ms_dirs = sorted(STATE_DIR.glob("integrations/microsoft*"))
    candidates: list[Path] = []
    for d in ms_dirs:
        candidates.append(d / f"token-{account}.json")
    for d in ms_dirs:
        candidates.append(d / "token-assistant.json")
    for d in ms_dirs:
        candidates.append(d / "token-microsoft.json")
    for d in ms_dirs:
        candidates.append(d / "token.json")

    for c in candidates:
        if c.exists():
            return c

    raise FileNotFoundError(
        f"No token file found for account '{account}'. Tried:\n"
        + "\n".join(f"  {c}" for c in dict.fromkeys(candidates))  # deduplicated
        + "\nRun: python3 sharepoint.py reauth   (or /ms-reauth in Telegram)"
    )

POLL_INTERVAL = 900   # 15 minutes
LOOK_AHEAD    = 14    # days

LOG_MAX_LINES = 1000
LOG_TRIM_TO   = 800   # keep newest 800 when limit hit (drops oldest 200)


# ---------------------------------------------------------------------------
# Logging (with rotation — max 1000 lines, trim to 800 on overflow)
# ---------------------------------------------------------------------------

def log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [calendar-poller] {msg}\n"
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
# Token helpers (copied from poll.py — same format, same token file)
# ---------------------------------------------------------------------------

def _write_token_atomic(path: Path, data: dict) -> None:
    """Write token JSON atomically via a temp file + rename."""
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _normalise_msal_cache(cache: dict) -> dict:
    """Convert MSAL token cache (PascalCase keys) to the simple flat format."""
    at_list  = list(cache.get("AccessToken",  {}).values())
    rt_list  = list(cache.get("RefreshToken", {}).values())
    app_list = list(cache.get("AppMetadata",  {}).values())
    if not rt_list:
        raise ValueError("No RefreshToken entry found in MSAL cache")
    at  = at_list[0]  if at_list  else {}
    rt  = rt_list[0]
    app = app_list[0] if app_list else {}
    return {
        "client_id":     at.get("client_id") or app.get("client_id", ""),
        "client_secret": "",
        "tenant_id":     at.get("realm", "common"),
        "refresh_token": rt["secret"],
        "access_token":  at.get("secret", ""),
    }


def _load_json_resilient(path: Path) -> dict:
    """Load JSON with auto-recovery from 'Extra data' corruption."""
    raw = path.read_text()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_err:
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(raw.strip())
            if isinstance(data, dict):
                log(f"WARNING: Token file corrupted (extra data at char {first_err.pos}). "
                    "Recovered and rewrote atomically.")
                _write_token_atomic(path, data)
                return data
        except json.JSONDecodeError:
            pass
        raise ValueError(
            f"Token file is unreadable and could not be auto-recovered: {path}\n"
            f"Original error: {first_err}\n"
            "Delete the file and re-authenticate."
        ) from first_err


def load_token() -> dict:
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"Token file not found: {TOKEN_FILE}\n"
            "Run the Microsoft auth flow first:\n"
            "  python3 sharepoint.py reauth   (or /ms-reauth in Telegram)"
        )
    data = _load_json_resilient(TOKEN_FILE)
    if "RefreshToken" in data and "AccessToken" in data:
        simple = _normalise_msal_cache(data)
        _write_token_atomic(TOKEN_FILE, simple)
        log("Converted MSAL token cache to simple format")
        return simple
    return data


def refresh_access_token(token_data: dict) -> str:
    tenant = token_data.get("tenant_id", "common")
    post_data: dict = {
        "client_id":     token_data["client_id"],
        "refresh_token": token_data["refresh_token"],
        "grant_type":    "refresh_token",
        "scope":         "Calendars.Read offline_access",
    }
    secret = token_data.get("client_secret", "")
    if secret:
        post_data["client_secret"] = secret

    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data=post_data,
        timeout=15,
    )
    resp.raise_for_status()
    try:
        new_data = resp.json()
    except Exception as e:
        raise ValueError(
            f"Token refresh failed: Microsoft returned non-JSON response "
            f"(status {resp.status_code}). Raw: {resp.text[:200]!r}\nError: {e}\n"
            "FLAG TO TOM: poll-calendar.py token refresh got unexpected response — check Microsoft auth."
        ) from e
    token_data["access_token"]  = new_data["access_token"]
    token_data["refresh_token"] = new_data.get("refresh_token", token_data["refresh_token"])
    _write_token_atomic(TOKEN_FILE, token_data)
    return token_data["access_token"]


# ---------------------------------------------------------------------------
# Calendar fetch
# ---------------------------------------------------------------------------

def fetch_events(access_token: str) -> list:
    now     = datetime.now(timezone.utc)
    end     = now + timedelta(days=LOOK_AHEAD)
    start_s = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_s   = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    url    = f"{GRAPH_BASE}/me/calendarView"
    params = {
        "startDateTime": start_s,
        "endDateTime":   end_s,
        "$orderby":      "start/dateTime asc",
        "$select":       "subject,start,end,location,attendees,bodyPreview",
        "$top":          50,
    }
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Prefer": "outlook.timezone=\"UTC\""},
        params=params,
        timeout=15,
    )
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "60"))
        log(f"Rate limited by Microsoft Graph — backing off {retry_after}s")
        time.sleep(retry_after)
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Prefer": "outlook.timezone=\"UTC\""},
            params=params,
            timeout=15,
        )
    resp.raise_for_status()
    try:
        return resp.json().get("value", [])
    except Exception as e:
        raise ValueError(
            f"Calendar fetch failed: Microsoft Graph returned non-JSON response "
            f"(status {resp.status_code}). Raw: {resp.text[:200]!r}\nError: {e}\n"
            "FLAG TO TOM: poll-calendar.py calendar fetch got unexpected response — check Microsoft auth or Graph API status."
        ) from e


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt_dt(dt_obj: dict) -> str:
    """Format a Graph dateTime object {'dateTime': '...', 'timeZone': '...'} for display."""
    raw = dt_obj.get("dateTime", "")
    if not raw:
        return "—"
    # Strip sub-seconds and trailing Z/timezone suffix for clean display
    raw = raw[:16].replace("T", " ")
    tz  = dt_obj.get("timeZone", "UTC")
    if tz and tz != "UTC":
        return f"{raw} {tz}"
    return f"{raw} UTC"


def _fmt_attendees(attendees: list) -> str:
    if not attendees:
        return "—"
    parts = []
    for a in attendees:
        email = a.get("emailAddress", {}).get("address", "")
        if email:
            parts.append(email)
    return ", ".join(parts) if parts else "—"


def format_event(evt: dict) -> str:
    subject   = evt.get("subject", "(no subject)")
    start     = _fmt_dt(evt.get("start", {}))
    end       = _fmt_dt(evt.get("end", {}))
    location  = (evt.get("location") or {}).get("displayName", "").strip() or "—"
    attendees = _fmt_attendees(evt.get("attendees", []))
    return (
        f"- **{subject}**\n"
        f"  {start} --> {end}\n"
        f"  Location: {location}\n"
        f"  Attendees: {attendees}\n"
    )


# ---------------------------------------------------------------------------
# Markdown output — atomic write
# ---------------------------------------------------------------------------

def write_calendar_md(events: list) -> None:
    CALENDAR_MD.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Outlook Calendar (Next {LOOK_AHEAD} Days)\n",
        f"Last updated: {ts}\n\n",
    ]
    formatted_count = 0
    if events:
        for evt in events:
            try:
                lines.append(format_event(evt))
                lines.append("\n")
                formatted_count += 1
            except Exception as e:
                evt_id = evt.get("id", "<unknown>") if isinstance(evt, dict) else "<unknown>"
                log(f"WARNING: Skipping malformed calendar event id={evt_id}: {e}")
    if not formatted_count:
        lines.append("_(no events in the next 14 days)_\n")

    content = "".join(lines)
    tmp = CALENDAR_MD.with_suffix(".tmp")
    try:
        tmp.write_text(content)
        tmp.replace(CALENDAR_MD)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _trim_log_on_startup() -> None:
    """If the log file already exceeds LOG_MAX_LINES, truncate it immediately on startup."""
    if not LOG_FILE.exists():
        return
    try:
        existing = LOG_FILE.read_text().splitlines(keepends=True)
    except OSError:
        return
    if len(existing) > LOG_MAX_LINES:
        trimmed = existing[-LOG_TRIM_TO:]
        tmp = LOG_FILE.with_suffix(".tmp")
        try:
            tmp.write_text("".join(trimmed))
            tmp.replace(LOG_FILE)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass


def main() -> None:
    global TOKEN_FILE

    p = argparse.ArgumentParser(description="OpenClaw Microsoft calendar poller")
    p.add_argument("--account",    default="assistant",
                   help="Account slug used to locate the token file "
                        "(default: assistant → token-assistant.json)")
    p.add_argument("--token-file", default=None,
                   help="Explicit path to OAuth token JSON (overrides --account lookup)")
    args = p.parse_args()

    try:
        TOKEN_FILE = _resolve_token_file(args.account, args.token_file)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _trim_log_on_startup()
    log(f"Calendar poller starting — account: {args.account}, token: {TOKEN_FILE}, output: {CALENDAR_MD}")

    while True:
        try:
            token_data   = load_token()
            access_token = refresh_access_token(token_data)
            events       = fetch_events(access_token)
            write_calendar_md(events)
            log(f"Poll complete — {len(events)} event(s) written to {CALENDAR_MD.name}")
        except FileNotFoundError as e:
            log(f"Token missing — exiting: {e}")
            sys.exit(1)
        except Exception as e:
            log(f"Poll error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

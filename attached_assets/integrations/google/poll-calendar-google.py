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
  python3 ~/.openclaw/integrations/google/poll-calendar-google.py --auth
  Open the printed consent URL on the phone and paste the full localhost
  callback URL into the waiting prompt.  The token is saved automatically.

Requires:
  pip3 install --break-system-packages google-auth google-auth-oauthlib google-api-python-client
"""

import sys
import os
import hmac
import tempfile
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

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
AUTH_PORT     = 8765  # Google Desktop OAuth loopback redirect port
AUTH_HOST     = "localhost"

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

def _auth_instructions():
    """Print the safe, interactive route needed to re-authorise a headless host."""
    log("FLAG TO TOM: Google Calendar needs re-authorisation.")
    log("  Run this on the gateway host (SSH in first if needed):")
    log(f"    python3 {__file__} --auth")
    log("  Open the printed Google consent URL on the phone, then paste the complete")
    log(f"  final {AUTH_HOST}:{AUTH_PORT} callback URL into the waiting auth prompt.")
    log("  The callback is validated locally; the OAuth library performs the token exchange.")


def _validate_callback_url(
    callback_url: str,
    expected_state: str,
    expected_port: int = AUTH_PORT,
) -> None:
    """Validate a Google loopback callback before exchanging it for tokens.

    Installed-app OAuth uses a loopback redirect.  A pasted callback is
    untrusted input, so keep the accepted origin exact and bind it to the
    state generated for this authorization attempt.  In particular, this does
    not accept arbitrary URLs, fragments, OOB values, or a code without state.
    """

    try:
        parsed = urlsplit(callback_url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Malformed OAuth callback URL") from exc

    if (
        parsed.scheme != "http"
        or parsed.hostname != AUTH_HOST
        or port != expected_port
        or parsed.path != "/"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("OAuth callback must be the expected localhost loopback URL")

    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("error"):
        raise ValueError("Google OAuth consent was not granted")

    code_values = query.get("code", [])
    state_values = query.get("state", [])
    if len(code_values) != 1 or not code_values[0]:
        raise ValueError("OAuth callback is missing its authorization code")
    if len(state_values) != 1 or not state_values[0]:
        raise ValueError("OAuth callback is missing its state")
    if not hmac.compare_digest(state_values[0], expected_state):
        raise ValueError("OAuth callback state does not match this authorization attempt")


def _oauthlib_authorization_response(callback_url: str, expected_state: str) -> str:
    """Return the validated loopback callback in oauthlib's accepted form.

    oauthlib's secure-transport guard rejects an HTTP authorization response,
    even though Google installed-app loopback redirects are intentionally HTTP.
    ``InstalledAppFlow.run_local_server`` works around the parser by rewriting
    the already-received local callback to HTTPS before calling ``fetch_token``.
    Keep that compatibility rewrite narrow: validate the original untrusted
    HTTP URL first, then rewrite only this exact localhost callback.  This does
    not disable TLS checks globally or change any network transport.
    """

    _validate_callback_url(callback_url, expected_state)
    return urlunsplit(
        ("https", f"{AUTH_HOST}:{AUTH_PORT}", "/", urlsplit(callback_url).query, "")
    )


def _complete_phone_auth(flow, read_callback=input, write_output=print):
    """Complete an installed-app OAuth flow from a phone's loopback callback.

    Google still redirects to the Desktop OAuth client's loopback URI.  The
    phone cannot resolve its own ``localhost`` to the gateway host, so the
    operator copies the full final URL into this process instead.  The OAuth
    library performs the normal authorization-code exchange and PKCE/state
    checks; no deprecated out-of-band redirect is used.
    """

    # Keep the redirect URI on the same installed-app loopback route used by
    # run_local_server, but complete the callback from stdin instead of
    # requiring the phone to reach the gateway host.
    flow.redirect_uri = f"http://{AUTH_HOST}:{AUTH_PORT}/"
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    write_output("Open this Google consent URL on the phone:")
    write_output(authorization_url)
    write_output(
        f"After consent, paste the complete final callback URL "
        f"(http://{AUTH_HOST}:{AUTH_PORT}/...) into this prompt."
    )
    callback_url = read_callback("Callback URL: ").strip()
    authorization_response = _oauthlib_authorization_response(callback_url, state)
    flow.fetch_token(authorization_response=authorization_response)
    return flow.credentials


def _write_token_file(path: Path, credentials) -> None:
    """Atomically write a token with owner-only permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            os.chmod(temporary.fileno(), 0o600)
            temporary.write(credentials.to_json())
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _require_refresh_token(credentials):
    """Require a refresh-capable credential before replacing an unattended token."""

    if not getattr(credentials, "refresh_token", None):
        raise ValueError(
            "Google OAuth did not return a refresh token; existing token was retained"
        )
    return credentials


def do_auth(read_callback=input, write_output=print):
    """
    Interactive OAuth flow for a headless gateway.
    Uses the provider's normal localhost redirect and a pasted callback URL.
    Call this via: python3 poll-calendar-google.py --auth
    """
    write_output("\n=== Google Calendar OAuth Setup ===")

    if not CREDENTIALS_FILE.exists():
        write_output("ERROR: Credentials file not found.")
        write_output(f"  Checked: {CREDENTIALS_FILE}")
        write_output(f"  Checked: {_GOOGLE_DIR}/gmail-credentials.json")
        write_output("  Download from Google Cloud Console → APIs & Services → Credentials")
        sys.exit(1)

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE),
            SCOPES,
            autogenerate_code_verifier=True,
        )
        creds = _require_refresh_token(
            _complete_phone_auth(
                flow,
                read_callback=read_callback,
                write_output=write_output,
            )
        )
        _write_token_file(TOKEN_FILE, creds)
        write_output(f"\nSUCCESS — token saved to {TOKEN_FILE}")
        write_output("Restart the service: systemctl --user restart openclaw-calendar-google.service")
        log(f"OAuth complete via --auth flag. Token saved to {TOKEN_FILE}")
    except Exception:
        # Do not echo provider responses: they can include callback material.
        write_output("\nERROR: OAuth flow failed; no token was written.")
        sys.exit(1)


def get_service():
    log(f"Using credentials: {CREDENTIALS_FILE.name}")
    log(f"Using token:       {TOKEN_FILE}")

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            log(f"WARNING: Could not read token file: {e} — treating as missing")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and not creds.refresh_token:
            log(
                "ERROR: Google Calendar credentials are expired and have no "
                "refresh token; unattended polling requires a refresh token."
            )
            _auth_instructions()
            return None
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _require_refresh_token(creds)
                _write_token_file(TOKEN_FILE, creds)
                log("Token refreshed successfully")
            except Exception as e:
                log(f"ERROR: Token refresh failed: {e}")
                if "invalid_grant" in str(e).lower():
                    log(
                        "Google rejected the refresh token (invalid_grant); "
                        "existing token.json was retained. Run --auth to replace it."
                    )
                _auth_instructions()
                return None
        else:
            # No usable token — need fresh auth. Only attempt in interactive mode.
            if not CREDENTIALS_FILE.exists():
                log("ERROR: Google credentials file not found.")
                log(f"  Checked: {_GOOGLE_DIR}/credentials.json")
                log(f"  Checked: {_GOOGLE_DIR}/gmail-credentials.json")
                log("  Download from Google Cloud Console → APIs & Services → Credentials")
                return None
            # Running as a systemd service (no TTY) — can't do interactive OAuth
            if not sys.stdin.isatty():
                log("ERROR: token.json missing and running as a service (no TTY) — cannot prompt for auth.")
                _auth_instructions()
                return None
            # Interactive fallback (should not normally reach here — use --auth flag)
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE),
                    SCOPES,
                    autogenerate_code_verifier=True,
                )
                creds = _require_refresh_token(_complete_phone_auth(flow))
                _write_token_file(TOKEN_FILE, creds)
                log(f"OAuth complete — token saved to {TOKEN_FILE}")
            except Exception:
                log("ERROR: OAuth flow failed; token was not written.")
                _auth_instructions()
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
    parser = argparse.ArgumentParser(description="Google Calendar poller for OpenClaw")
    parser.add_argument(
        "--auth",
        action="store_true",
        help=(
            "Run interactive OAuth setup and paste the full localhost callback URL"
        ),
    )
    args = parser.parse_args()

    if args.auth:
        do_auth()
        return

    log("Google Calendar poller started")
    while True:
        try:
            poll_once()
        except Exception as e:
            log(f"ERROR: Unhandled exception in poll cycle: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

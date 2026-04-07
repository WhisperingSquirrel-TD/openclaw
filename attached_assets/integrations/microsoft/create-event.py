#!/usr/bin/env python3
"""
Microsoft Graph API calendar event creator for OpenClaw.

Creates a calendar event (optionally a Teams meeting) from the
assistant@ or personal Microsoft account using a stored OAuth token.

Usage:
  create-event.py --start "2026-04-08T10:00" --end "2026-04-08T11:00" \
      --title-file /tmp/oc-event-title.txt \
      --attendees-file /tmp/oc-event-attendees.txt \
      --teams

  All file arguments avoid embedding user content in the shell command,
  which prevents accidental matches against exec security denylist patterns.

Arguments:
  --title <str>             Event title (overridden by --title-file if given)
  --title-file <path>       Read event title from this file
  --start <ISO datetime>    Start time — YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS
  --end <ISO datetime>      End time   — YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS
  --duration <minutes>      Duration in minutes (used if --end not given, default 60)
  --attendees <emails>      Comma-separated email addresses
  --attendees-file <path>   Read attendees from this file (one email per line or comma-sep)
  --timezone <tz>           IANA timezone (default: Europe/London)
  --teams                   Add Teams online meeting link (default: true)
  --no-teams                Do not add Teams link
  --account <slug>          Token account slug (default: assistant)
  --token-file <path>       Explicit token file path

Exit codes:
  0  Success
  1  Auth error (token missing / refresh failed)
  2  API error (Graph rejected the request)
  3  Bad arguments
"""
import argparse
import json
import sys
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_DIR  = Path.home() / ".openclaw"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenClaw Microsoft Graph calendar event creator")
    p.add_argument("--title",          default="",
                   help="Event title (overridden by --title-file)")
    p.add_argument("--title-file",     default=None,
                   help="Read event title from this file")
    p.add_argument("--start",          required=True,
                   help="Start datetime: YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS")
    p.add_argument("--end",            default=None,
                   help="End datetime: YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS")
    p.add_argument("--duration",       type=int, default=60,
                   help="Duration in minutes when --end is not given (default 60)")
    p.add_argument("--attendees",      default="",
                   help="Comma-separated attendee emails (overridden by --attendees-file)")
    p.add_argument("--attendees-file", default=None,
                   help="Read attendee emails from this file (one per line or comma-separated)")
    p.add_argument("--timezone",       default="Europe/London",
                   help="IANA timezone name (default: Europe/London)")
    p.add_argument("--teams",          action="store_true", default=True,
                   help="Include a Teams online meeting link (default: on)")
    p.add_argument("--no-teams",       action="store_true", default=False,
                   help="Do not add a Teams link")
    p.add_argument("--account",        default="assistant",
                   help="Account slug for token lookup (default: assistant)")
    p.add_argument("--token-file",     default=None,
                   help="Explicit path to OAuth token JSON file")
    return p.parse_args()


def resolve_token_file(args: argparse.Namespace) -> Path:
    if args.token_file:
        return Path(args.token_file)
    candidates = [
        STATE_DIR / f"integrations/microsoft/token-{args.account}.json",
        STATE_DIR / f"integrations/microsoft-{args.account}/token-{args.account}.json",
        STATE_DIR / "integrations/microsoft/token-microsoft.json",
        STATE_DIR / "integrations/microsoft/token.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"No token file found for account '{args.account}'. Tried:\n"
        + "\n".join(f"  {c}" for c in candidates)
        + "\nRun the Microsoft auth flow first."
    )


def _write_token_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _load_json_resilient(path: Path) -> dict:
    raw = path.read_text()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_err:
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(raw.strip())
            if isinstance(data, dict):
                print(f"WARNING: Token file corrupted — auto-recovered.", file=sys.stderr)
                _write_token_atomic(path, data)
                return data
        except json.JSONDecodeError:
            pass
        raise ValueError(
            f"Token file unreadable: {path}\nError: {first_err}\n"
            "Delete the file and re-authenticate."
        ) from first_err


def load_token(token_file: Path) -> dict:
    data = _load_json_resilient(token_file)
    if "RefreshToken" in data and "AccessToken" in data:
        at_list  = list(data.get("AccessToken",  {}).values())
        rt_list  = list(data.get("RefreshToken", {}).values())
        app_list = list(data.get("AppMetadata",  {}).values())
        at  = at_list[0]  if at_list  else {}
        rt  = rt_list[0]
        app = app_list[0] if app_list else {}
        simple = {
            "client_id":     at.get("client_id") or app.get("client_id", ""),
            "client_secret": "",
            "tenant_id":     at.get("realm", "common"),
            "refresh_token": rt["secret"],
            "access_token":  at.get("secret", ""),
        }
        _write_token_atomic(token_file, simple)
        return simple
    return data


def refresh_access_token(token_data: dict, token_file: Path) -> str:
    tenant = token_data.get("tenant_id", "common")
    post_data: dict = {
        "client_id":     token_data["client_id"],
        "refresh_token": token_data["refresh_token"],
        "grant_type":    "refresh_token",
        "scope":         "Calendars.ReadWrite offline_access",
    }
    secret = token_data.get("client_secret", "")
    if secret:
        post_data["client_secret"] = secret

    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data=post_data,
        timeout=15,
    )
    if not resp.ok:
        print(f"Token refresh failed: {resp.status_code} {resp.text}", file=sys.stderr)
        print(
            "If you see 'invalid_grant' or 'AADSTS65001', the token does not have "
            "Calendars.ReadWrite scope. Re-run the Microsoft auth flow and grant calendar "
            "read+write permission.",
            file=sys.stderr,
        )
        sys.exit(1)

    new_data = resp.json()
    token_data["access_token"]  = new_data["access_token"]
    token_data["refresh_token"] = new_data.get("refresh_token", token_data["refresh_token"])
    _write_token_atomic(token_file, token_data)
    return token_data["access_token"]


def parse_datetime(dt_str: str) -> str:
    """Normalise a datetime string to YYYY-MM-DDTHH:MM:SS for Graph API."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(dt_str.strip(), fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {dt_str!r}. Use YYYY-MM-DDTHH:MM format.")


def parse_attendees(raw: str) -> list[str]:
    emails = []
    for part in raw.replace("\n", ",").split(","):
        email = part.strip()
        if email and "@" in email:
            emails.append(email)
    return emails


def create_event(
    access_token: str,
    title: str,
    start_dt: str,
    end_dt: str,
    attendees: list[str],
    tz: str,
    teams: bool,
) -> dict:
    payload: dict = {
        "subject": title,
        "start":   {"dateTime": start_dt, "timeZone": tz},
        "end":     {"dateTime": end_dt,   "timeZone": tz},
        "attendees": [
            {
                "emailAddress": {"address": email},
                "type": "required",
            }
            for email in attendees
        ],
    }
    if teams:
        payload["isOnlineMeeting"] = True
        payload["onlineMeetingProvider"] = "teamsForBusiness"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    resp = requests.post(
        f"{GRAPH_BASE}/me/events",
        headers=headers,
        json=payload,
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        print(f"Event creation failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(2)
    return resp.json()


def main() -> None:
    args = parse_args()

    # Resolve title
    title = args.title
    if args.title_file:
        try:
            title = Path(args.title_file).read_text(encoding="utf-8").strip()
        except OSError as e:
            print(f"ERROR: Cannot read --title-file: {e}", file=sys.stderr)
            sys.exit(3)
    if not title:
        print("ERROR: --title or --title-file is required.", file=sys.stderr)
        sys.exit(3)

    # Resolve attendees
    attendee_raw = args.attendees
    if args.attendees_file:
        try:
            attendee_raw = Path(args.attendees_file).read_text(encoding="utf-8")
        except OSError as e:
            print(f"ERROR: Cannot read --attendees-file: {e}", file=sys.stderr)
            sys.exit(3)
    attendees = parse_attendees(attendee_raw)

    # Resolve datetimes
    try:
        start_dt = parse_datetime(args.start)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(3)

    if args.end:
        try:
            end_dt = parse_datetime(args.end)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(3)
    else:
        start_obj = datetime.strptime(start_dt, "%Y-%m-%dT%H:%M:%S")
        end_obj   = start_obj + timedelta(minutes=args.duration)
        end_dt    = end_obj.strftime("%Y-%m-%dT%H:%M:%S")

    teams = args.teams and not args.no_teams

    # Auth
    try:
        token_file = resolve_token_file(args)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    token_data   = load_token(token_file)
    access_token = refresh_access_token(token_data, token_file)

    # Create
    event = create_event(access_token, title, start_dt, end_dt, attendees, args.timezone, teams)

    join_url = ""
    if teams:
        join_url = (event.get("onlineMeeting") or {}).get("joinUrl", "")

    print(f"Event created: {title}")
    print(f"  Start:     {start_dt} ({args.timezone})")
    print(f"  End:       {end_dt}")
    print(f"  Attendees: {', '.join(attendees) if attendees else '(none)'}")
    if join_url:
        print(f"  Teams URL: {join_url}")
    print(f"  Event ID:  {event.get('id', 'unknown')}")


if __name__ == "__main__":
    main()

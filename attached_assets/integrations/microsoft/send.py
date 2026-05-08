#!/usr/bin/env python3
"""
Microsoft Graph API email sender for OpenClaw.

Sends email using a stored OAuth refresh token — no browser or interactive
auth required. Uses the same token file as poll.py and refreshes automatically.

Usage:
  send.py <to> <from_name> <subject> <body> [reply_to_message_id]

  to                  Recipient email address(es) — comma-separated for
                      multiple recipients (all on the same email, not separate)
  from_name           Display name for the From field (e.g. "PA to Tom Dean")
  subject             Email subject
  body                Email body (plain text; use \\n for newlines)
  reply_to_message_id (optional) Microsoft message ID to thread the reply to

Options:
  --account <slug>         Account slug to locate the token file (e.g. "assistant",
                           "microsoft")
  --token-file <path>      Explicit path to OAuth token JSON file
  --recipients-file <path> Read To: recipients from this file — one per line or
                           comma-separated. Overrides the <to> positional arg.
                           All addresses end up on the SAME email (not separate sends).
  --subject-file <path>    Read subject from this file (overrides subject positional arg)
  --body-file <path>       Read body from this file (overrides body positional arg).
                           Avoids passing large/sensitive content as a shell argument.
  --whoami                 Print the authenticated email address for the resolved
                           token file and exit. Use to verify which account a token
                           file actually belongs to.

Exit codes:
  0  Success
  1  Auth error (token missing, expired refresh token)
  2  Send error (Graph API rejected the request)
  3  Bad arguments
"""
import argparse
import json
import sys
import requests
from pathlib import Path

STATE_DIR  = Path.home() / ".openclaw"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenClaw Microsoft Graph email sender")
    p.add_argument("to",        nargs="?", default=None,
                   help="Recipient email address(es) — comma-separated for multiple "
                        "(overridden by --recipients-file if given)")
    p.add_argument("from_name", nargs="?", default=None, help="Display name for the From field")
    p.add_argument("subject",   nargs="?", default="",
                   help="Email subject (overridden by --subject-file if given)")
    p.add_argument("body",      nargs="?", default="",
                   help="Email body plain text, \\n for newlines (overridden by --body-file if given)")
    p.add_argument("reply_to_message_id", nargs="?", default=None,
                   help="Microsoft message ID to thread as a reply")
    p.add_argument("--account",          default=None,
                   help="Account slug (used to locate token file)")
    p.add_argument("--token-file",       default=None,
                   help="Explicit path to OAuth token JSON file")
    p.add_argument("--whoami",           action="store_true",
                   help="Print the authenticated email for the resolved token and exit")
    p.add_argument("--recipients-file",  default=None,
                   help="Read To: recipients from this file — one per line or comma-separated. "
                        "All addresses go on ONE email. Overrides <to> positional arg.")
    p.add_argument("--subject-file",     default=None,
                   help="Read subject from this file (overrides subject positional arg)")
    p.add_argument("--body-file",        default=None,
                   help="Read body from this file (overrides body positional arg). "
                        "Avoids passing large/sensitive content as a shell argument.")
    return p.parse_args()


def parse_recipients(raw: str) -> list[str]:
    """Parse a comma- or newline-separated list of email addresses."""
    addresses = []
    for part in raw.replace("\n", ",").split(","):
        addr = part.strip()
        if addr and "@" in addr:
            addresses.append(addr)
    return addresses


def resolve_token_file(args: argparse.Namespace) -> Path:
    if args.token_file:
        return Path(args.token_file)

    integrations_dir = STATE_DIR / "integrations"

    # All microsoft* subdirectories — longer names (e.g. microsoft-l1) before
    # the base microsoft/ dir so account-specific tokens take priority.
    ms_dirs = sorted(
        integrations_dir.glob("microsoft*/"),
        key=lambda p: (-len(p.name), p.name),
    ) if integrations_dir.exists() else []

    candidates = []

    if args.account:
        # Search every microsoft* dir for token-{account}.json
        for d in ms_dirs:
            candidates.append(d / f"token-{args.account}.json")

    # Generic fallbacks: token-microsoft.json then token.json across all microsoft* dirs
    for d in ms_dirs:
        candidates.append(d / "token-microsoft.json")
    for d in ms_dirs:
        candidates.append(d / "token.json")

    for c in candidates:
        if c.exists():
            return c

    raise FileNotFoundError(
        f"No token file found for account '{args.account}'. Tried:\n"
        + "\n".join(f"  {c}" for c in candidates)
        + "\nRun the Microsoft auth flow first."
    )


def _write_token_atomic(path: Path, data: dict) -> None:
    """Write token JSON atomically via temp file + rename.
    Prevents the 'Extra data' JSON corruption caused by interrupted writes."""
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


def _load_json_resilient(path: Path) -> dict:
    """Load JSON with automatic recovery from 'Extra data' corruption."""
    raw = path.read_text()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_err:
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(raw.strip())
            if isinstance(data, dict):
                print(f"WARNING: Token file corrupted (extra data at char {first_err.pos}). "
                      "Auto-recovered and rewrote atomically.", file=sys.stderr)
                _write_token_atomic(path, data)
                return data
        except json.JSONDecodeError:
            pass
        raise ValueError(
            f"Token file unreadable and cannot be auto-recovered: {path}\n"
            f"Error: {first_err}\nDelete the file and re-recovered."
        ) from first_err


def load_token(token_file: Path) -> dict:
    data = _load_json_resilient(token_file)
    # Handle MSAL cache format
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
        "scope":         "Mail.Send offline_access",
    }
    # Only include client_secret for confidential clients
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
        sys.exit(1)

    new_data = resp.json()
    token_data["access_token"]  = new_data["access_token"]
    token_data["refresh_token"] = new_data.get("refresh_token", token_data["refresh_token"])
    _write_token_atomic(token_file, token_data)
    return token_data["access_token"]


def whoami(access_token: str) -> None:
    """Print the email address the token belongs to and exit."""
    resp = requests.get(
        f"{GRAPH_BASE}/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if not resp.ok:
        print(f"whoami failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    email = data.get("mail") or data.get("userPrincipalName") or "(unknown)"
    name  = data.get("displayName", "")
    print(f"{email}  ({name})")


def send_email(
    access_token: str,
    recipients: list[str],
    from_name: str,
    subject: str,
    body: str,
    reply_to_message_id: str | None = None,
) -> None:
    if not recipients:
        print("ERROR: no valid recipient addresses found", file=sys.stderr)
        sys.exit(3)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    # All recipients go on ONE email — never loop and send separately.
    to_recipients = [{"emailAddress": {"address": addr}} for addr in recipients]

    message: dict = {
        "subject": subject,
        "body": {
            "contentType": "Text",
            "content":      body.replace("\\n", "\n"),
        },
        "toRecipients": to_recipients,
    }

    if reply_to_message_id:
        # Use createReply endpoint to properly thread the email
        create_url = f"{GRAPH_BASE}/me/messages/{reply_to_message_id}/createReply"
        resp = requests.post(create_url, headers=headers, timeout=15)
        if not resp.ok:
            print(f"createReply failed: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(2)
        draft = resp.json()
        draft_id = draft["id"]

        # Update the draft with our content
        update_url = f"{GRAPH_BASE}/me/messages/{draft_id}"
        resp = requests.patch(update_url, headers=headers, json={
            "subject":      subject,
            "body":         message["body"],
            "toRecipients": to_recipients,
        }, timeout=15)
        if not resp.ok:
            print(f"Draft update failed: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(2)

        # Send the draft
        send_url = f"{GRAPH_BASE}/me/messages/{draft_id}/send"
        resp = requests.post(send_url, headers=headers, timeout=15)
    else:
        # Send directly
        payload = {"message": message, "saveToSentItems": True}
        resp = requests.post(
            f"{GRAPH_BASE}/me/sendMail",
            headers=headers,
            json=payload,
            timeout=15,
        )

    if resp.status_code in (200, 202, 204):
        to_display = ", ".join(recipients)
        print(f"Email sent to: {to_display}")
    else:
        print(f"Send failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(2)


def main() -> None:
    args = parse_args()
    try:
        token_file = resolve_token_file(args)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    token_data   = load_token(token_file)
    access_token = refresh_access_token(token_data, token_file)

    if args.whoami:
        print(f"Token file: {token_file}")
        whoami(access_token)
        sys.exit(0)

    if not args.from_name:
        print("ERROR: from_name is required when sending email", file=sys.stderr)
        sys.exit(3)

    # Resolve recipients — file takes priority over positional arg.
    recipient_raw = args.to or ""
    if args.recipients_file:
        try:
            recipient_raw = Path(args.recipients_file).read_text(encoding="utf-8")
        except OSError as e:
            print(f"ERROR: Cannot read --recipients-file {args.recipients_file}: {e}", file=sys.stderr)
            sys.exit(3)

    recipients = parse_recipients(recipient_raw)
    if not recipients:
        print("ERROR: at least one recipient is required (positional <to> or --recipients-file)",
              file=sys.stderr)
        sys.exit(3)

    # Resolve subject and body — file flags take priority over positional args.
    subject = args.subject
    if args.subject_file:
        try:
            subject = Path(args.subject_file).read_text(encoding="utf-8").strip()
        except OSError as e:
            print(f"ERROR: Cannot read --subject-file {args.subject_file}: {e}", file=sys.stderr)
            sys.exit(3)

    body = args.body
    if args.body_file:
        try:
            body = Path(args.body_file).read_text(encoding="utf-8")
        except OSError as e:
            print(f"ERROR: Cannot read --body-file {args.body_file}: {e}", file=sys.stderr)
            sys.exit(3)

    if not subject:
        print("ERROR: subject is required (positional arg or --subject-file)", file=sys.stderr)
        sys.exit(3)
    if not body:
        print("ERROR: body is required (positional arg or --body-file)", file=sys.stderr)
        sys.exit(3)

    send_email(
        access_token,
        recipients=recipients,
        from_name=args.from_name,
        subject=subject,
        body=body,
        reply_to_message_id=args.reply_to_message_id,
    )


if __name__ == "__main__":
    main()

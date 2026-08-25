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
  body                Email body (plain text; use \\n for line breaks)
  reply_to_message_id (optional) Microsoft message ID to thread the reply to

Options:
  --account <slug>         Account slug to locate the token file (e.g. "assistant",
                           "microsoft")
  --token-file <path>      Explicit path to OAuth token JSON file
  --recipients-file <path> Read To: recipients from this file — one per line or
                           comma-separated. Overrides the <to> positional arg.
                           All addresses end up on the SAME email (not separate sends).
  --bcc <addresses>        BCC recipient address(es), comma-separated.
  --bcc-file <path>        Read BCC recipients from this file — one per line or
                           comma-separated. Adds Graph bccRecipients.
  --subject-file <path>    Read subject from this file (overrides subject positional arg)
  --body-file <path>       Read body from this file (overrides body positional arg).
                           Avoids passing large/sensitive content as a shell argument.
  --body-content-type <t>  Body type: text (default) or html.
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
import base64
import fcntl
import hashlib
import hmac
import json
import mimetypes
import os
import sys
import time
import requests
from pathlib import Path

STATE_DIR  = Path.home() / ".openclaw"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TASK_DISPATCH_AUDIENCE = "openclaw.microsoft.email.send"
TASK_DISPATCH_KEY_ENV = "TASK_SYSTEM_EMAIL_DISPATCH_KEY"
TASK_DISPATCH_MAX_TTL_SECONDS = 15 * 60
TASK_DISPATCH_STATE_PATH = STATE_DIR / "integrations" / "microsoft" / "task-dispatch-used.json"
TASK_DISPATCH_LOCK_PATH = STATE_DIR / "integrations" / "microsoft" / "task-dispatch-used.lock"
TASK_DISPATCH_AUDIT_PATH = STATE_DIR / "integrations" / "microsoft" / "task-dispatch-audit.log"


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
    p.add_argument("--reply-all", action="store_true",
                   help="When replying to an existing message, preserve reply-all rather than reply")
    p.add_argument("--account",          default=None,
                   help="Account slug (used to locate token file)")
    p.add_argument("--token-file",       default=None,
                   help="Explicit path to OAuth token JSON file")
    p.add_argument("--whoami",           action="store_true",
                   help="Print the authenticated email for the resolved token and exit")
    p.add_argument("--recipients-file",  default=None,
                   help="Read To: recipients from this file — one per line or comma-separated. "
                        "All addresses go on ONE email. Overrides <to> positional arg.")
    p.add_argument("--bcc",              default="",
                   help="BCC recipient email address(es) — comma-separated for multiple")
    p.add_argument("--bcc-file",         default=None,
                   help="Read BCC recipients from this file — one per line or comma-separated. "
                        "All addresses go on ONE email as bccRecipients.")
    p.add_argument("--cc",               default="",
                    help="CC recipient address(es) — comma-separated for multiple")
    p.add_argument("--cc-file",          default=None,
                    help="Read CC recipients from this file — one per line or comma-separated. "
                         "All addresses go on ONE email as ccRecipients.")
    p.add_argument("--subject-file",     default=None,
                   help="Read subject from this file (overrides subject positional arg)")
    p.add_argument("--body-file",        default=None,
                   help="Read body from this file (overrides body positional arg). "
                        "Avoids passing large/sensitive content as a shell argument.")
    p.add_argument("--body-content-type", default="text", choices=["text","html"],
                   help="Body type for Microsoft Graph message body")
    p.add_argument("--attachment", action="append", default=[],
                   help="Path to file to attach. Can be repeated.")
    p.add_argument("--task-dispatch-permit", default=None,
                    help="Path to a signed, single-use task-system dispatch permit. "
                         "It is bound to the exact email and is valid only after "
                         "the task system has recorded owner sign-off.")
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


def refresh_access_token(token_data: dict, token_file: Path, scope: str = "Mail.Send offline_access") -> str:
    tenant = token_data.get("tenant_id", "common")
    post_data: dict = {
        "client_id":     token_data["client_id"],
        "refresh_token": token_data["refresh_token"],
        "grant_type":    "refresh_token",
        "scope":         scope,
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


def _build_attachment_snapshot(paths: list[str]) -> tuple[list[dict], list[dict]]:
    """Read attachment bytes once for both Graph upload and permit binding."""
    attachments = []
    fingerprints = []
    for raw in paths:
        if not raw:
            continue
        p = Path(raw)
        if not p.exists() or not p.is_file():
            print(f"ERROR: attachment not found: {p}", file=sys.stderr)
            sys.exit(3)
        data = p.read_bytes()
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": p.name,
            "contentType": mime,
            "contentBytes": base64.b64encode(data).decode("ascii"),
        })
        fingerprints.append({
            "name": p.name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return attachments, sorted(fingerprints, key=lambda item: (item["name"], item["sha256"]))


def _canonical_json(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _normalise_addresses(addresses: list[str]) -> list[str]:
    return sorted(addr.strip().lower() for addr in addresses if addr.strip())


def email_fingerprint(
    recipients: list[str],
    cc_recipients: list[str],
    bcc_recipients: list[str],
    from_name: str,
    subject: str,
    body: str,
    body_content_type: str,
    reply_to_message_id: str | None,
    reply_all: bool,
    attachment_fingerprints: list[dict],
) -> str:
    """Hash the exact email fields a task-system sign-off is allowed to authorise."""
    graph_body = body if body_content_type.lower() == "html" else body.replace("\\n", "\n")
    canonical_email = {
        "attachments": attachment_fingerprints,
        "bcc": _normalise_addresses(bcc_recipients),
        "cc": _normalise_addresses(cc_recipients),
        "body": graph_body,
        "body_content_type": body_content_type.lower(),
        "from_name": from_name,
        "reply_all": bool(reply_all),
        "reply_to_message_id": reply_to_message_id or "",
        "subject": subject,
        "to": _normalise_addresses(recipients),
    }
    return hashlib.sha256(_canonical_json(canonical_email)).hexdigest()


def _task_dispatch_audit(event: str, *, task_id: str | None = None,
                         permit_id: str | None = None, detail: str | None = None) -> None:
    """Write a small local audit record without email content or recipient data."""
    TASK_DISPATCH_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": int(time.time()),
        "event": event,
        "task_id": task_id,
        "permit_id": permit_id,
        "detail": detail,
    }
    with TASK_DISPATCH_AUDIT_PATH.open("a", encoding="utf-8") as audit_file:
        audit_file.write(json.dumps(entry, sort_keys=True) + "\n")


def _load_task_dispatch_key() -> bytes:
    key = os.environ.get(TASK_DISPATCH_KEY_ENV, "")
    if len(key.encode("utf-8")) < 32:
        raise ValueError(
            f"{TASK_DISPATCH_KEY_ENV} must be configured with at least 32 bytes for task dispatch"
        )
    return key.encode("utf-8")


def _read_used_permits() -> dict:
    try:
        raw = TASK_DISPATCH_STATE_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        raise ValueError("task dispatch replay ledger is unreadable")


def _write_used_permits(used: dict) -> None:
    tmp_path = TASK_DISPATCH_STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(used, sort_keys=True), encoding="utf-8")
    tmp_path.replace(TASK_DISPATCH_STATE_PATH)


def verify_and_consume_task_dispatch_permit(permit_path: str, expected_email_digest: str) -> dict:
    """Validate and atomically consume a task-system email dispatch permit."""
    try:
        permit = json.loads(Path(permit_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _task_dispatch_audit("permit_blocked", detail="permit_unreadable")
        raise ValueError("task dispatch permit is unreadable") from exc

    if not isinstance(permit, dict):
        _task_dispatch_audit("permit_blocked", detail="permit_not_object")
        raise ValueError("task dispatch permit must be a JSON object")

    signature = permit.pop("signature", None)
    task_id = permit.get("task_id") if isinstance(permit.get("task_id"), str) else None
    draft_id = permit.get("draft_id") if isinstance(permit.get("draft_id"), str) else None
    permit_id = permit.get("jti") if isinstance(permit.get("jti"), str) else None
    try:
        if permit.get("version") != 1:
            raise ValueError("unsupported permit version")
        if permit.get("audience") != TASK_DISPATCH_AUDIENCE:
            raise ValueError("permit audience is invalid")
        if not task_id or not draft_id or not permit_id or not isinstance(signature, str):
            raise ValueError("permit is missing required claims")
        expires_at = permit.get("expires_at")
        if type(expires_at) is not int:
            raise ValueError("permit expiry is invalid")
        now = int(time.time())
        if expires_at <= now:
            raise ValueError("permit has expired")
        if expires_at > now + TASK_DISPATCH_MAX_TTL_SECONDS:
            raise ValueError("permit expiry exceeds the allowed lifetime")
        if permit.get("email_digest") != expected_email_digest:
            raise ValueError("permit does not match the exact email being sent")
        expected_signature = hmac.new(
            _load_task_dispatch_key(), _canonical_json(permit), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("permit signature is invalid")
    except ValueError as exc:
        _task_dispatch_audit("permit_blocked", task_id=task_id, permit_id=permit_id, detail=str(exc))
        raise

    TASK_DISPATCH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TASK_DISPATCH_LOCK_PATH.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            used = _read_used_permits()
            if permit_id in used:
                _task_dispatch_audit(
                    "permit_blocked", task_id=task_id, permit_id=permit_id, detail="permit_replayed"
                )
                raise ValueError("task dispatch permit was already used")
            used[permit_id] = {"task_id": task_id, "consumed_at": int(time.time())}
            _write_used_permits(used)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    _task_dispatch_audit("permit_consumed", task_id=task_id, permit_id=permit_id)
    return {"task_id": task_id, "permit_id": permit_id}


def send_email(
    access_token: str,
    recipients: list[str],
    from_name: str,
    subject: str,
    body: str,
    body_content_type: str = "text",
    reply_to_message_id: str | None = None,
    attachments: list[dict] | None = None,
    reply_all: bool = False,
    bcc_recipients: list[str] | None = None,
    cc_recipients: list[str] | None = None,
) -> None:
    bcc_recipients = bcc_recipients or []
    cc_recipients = cc_recipients or []
    if not recipients and not bcc_recipients:
        print("ERROR: no valid To or BCC recipient addresses found", file=sys.stderr)
        sys.exit(3)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    # All recipients go on ONE email — never loop and send separately.
    to_recipients = [{"emailAddress": {"address": addr}} for addr in recipients]
    graph_bcc_recipients = [{"emailAddress": {"address": addr}} for addr in bcc_recipients]
    graph_cc_recipients = [{"emailAddress": {"address": addr}} for addr in cc_recipients]

    graph_body_type = "HTML" if body_content_type.lower() == "html" else "Text"
    message: dict = {
        "subject": subject,
        "body": {
            "contentType": graph_body_type,
            "content": body if graph_body_type == "HTML" else body.replace("\\n", "\n"),
        },
        "toRecipients": to_recipients,
    }
    if graph_bcc_recipients:
        message["bccRecipients"] = graph_bcc_recipients
    if graph_cc_recipients:
        message["ccRecipients"] = graph_cc_recipients
    if attachments:
        message["attachments"] = attachments

    if reply_to_message_id:
        # Use createReply / createReplyAll endpoint to properly preserve thread context
        reply_endpoint = "createReplyAll" if reply_all else "createReply"
        create_url = f"{GRAPH_BASE}/me/messages/{reply_to_message_id}/{reply_endpoint}"
        resp = requests.post(create_url, headers=headers, timeout=15)
        if not resp.ok:
            print(f"createReply failed: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(2)
        draft = resp.json()
        draft_id = draft["id"]

        # Update the draft with our content
        update_url = f"{GRAPH_BASE}/me/messages/{draft_id}"
        draft_patch = {
            "subject": subject,
            "body": message["body"],
            "toRecipients": to_recipients,
            # Prevent a reply-all draft retaining recipients outside the signed-off draft.
            "ccRecipients": graph_cc_recipients,
            "bccRecipients": graph_bcc_recipients,
        }
        if attachments:
            draft_patch["attachments"] = attachments
        resp = requests.patch(update_url, headers=headers, json=draft_patch, timeout=15)
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
        to_display = ", ".join(recipients) if recipients else "(none)"
        bcc_display = ", ".join(bcc_recipients) if bcc_recipients else "(none)"
        print(f"Email sent. To: {to_display}; BCC: {bcc_display}")
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

    bcc_raw = args.bcc or ""
    if args.bcc_file:
        try:
            bcc_raw = Path(args.bcc_file).read_text(encoding="utf-8")
        except OSError as e:
            print(f"ERROR: Cannot read --bcc-file {args.bcc_file}: {e}", file=sys.stderr)
            sys.exit(3)
    bcc_recipients = parse_recipients(bcc_raw)

    cc_raw = args.cc or ""
    if args.cc_file:
        try:
            cc_raw = Path(args.cc_file).read_text(encoding="utf-8")
        except OSError as e:
            print(f"ERROR: Cannot read --cc-file {args.cc_file}: {e}", file=sys.stderr)
            sys.exit(3)
    cc_recipients = parse_recipients(cc_raw)

    if not recipients and not bcc_recipients:
        print("ERROR: at least one To or BCC recipient is required (positional <to>, --recipients-file, --bcc, or --bcc-file)",
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

    attachments, attachment_fingerprints = _build_attachment_snapshot(args.attachment)
    permit_context = None
    if args.task_dispatch_permit:
        try:
            permit_context = verify_and_consume_task_dispatch_permit(
                args.task_dispatch_permit,
                email_fingerprint(
                    recipients=recipients,
                    cc_recipients=cc_recipients,
                    bcc_recipients=bcc_recipients,
                    from_name=args.from_name,
                    subject=subject,
                    body=body,
                    body_content_type=args.body_content_type,
                    reply_to_message_id=args.reply_to_message_id,
                    reply_all=args.reply_all,
                    attachment_fingerprints=attachment_fingerprints,
                ),
            )
        except ValueError as exc:
            print(f"ERROR: task-system email dispatch blocked: {exc}", file=sys.stderr)
            sys.exit(3)

    try:
        send_email(
            access_token,
            recipients=recipients,
            from_name=args.from_name,
            subject=subject,
            body=body,
            body_content_type=args.body_content_type,
            reply_to_message_id=args.reply_to_message_id,
            attachments=attachments,
            reply_all=args.reply_all,
            bcc_recipients=bcc_recipients,
            cc_recipients=cc_recipients,
        )
    except SystemExit:
        if permit_context:
            _task_dispatch_audit(
                "dispatch_failed",
                task_id=permit_context["task_id"],
                permit_id=permit_context["permit_id"],
            )
        raise
    else:
        if permit_context:
            _task_dispatch_audit(
                "dispatch_sent",
                task_id=permit_context["task_id"],
                permit_id=permit_context["permit_id"],
            )


if __name__ == "__main__":
    main()

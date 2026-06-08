#!/usr/bin/env python3
"""
Trusted Gmail Reader for OpenClaw
Reads full Gmail bodies and downloads attachments for approved senders.

Usage:
    python3 read_gmail.py <gmail_message_id> [--download-attachments]

Security:
    - Checks actual sender against ~/.openclaw/integrations/known-contacts.txt
    - Refuses non-approved senders
    - Uses existing Gmail readonly token
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

import requests

STATE_DIR = Path.home() / ".openclaw"
CONTACTS_FILE = STATE_DIR / "integrations/known-contacts.txt"
TOKEN_FILE = STATE_DIR / "integrations/google/gmail-token.json"
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
DEFAULT_ATTACHMENT_DIR = STATE_DIR / "workspace/expense-attachments-gmail"


def die(msg: str, code: int = 2) -> None:
    print(json.dumps({"error": msg}), file=sys.stderr)
    raise SystemExit(code)


def load_known_contacts() -> set[str]:
    if not CONTACTS_FILE.exists():
        return set()
    lines = CONTACTS_FILE.read_text(encoding="utf-8").splitlines()
    return {l.strip().lower() for l in lines if l.strip() and not l.strip().startswith("#")}


def load_token() -> dict[str, Any]:
    if not TOKEN_FILE.exists():
        die(f"Token file not found: {TOKEN_FILE}")
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"Failed to load Gmail token: {e}")


def save_token(token: dict[str, Any]) -> None:
    TOKEN_FILE.write_text(json.dumps(token), encoding="utf-8")


def refresh_access_token(token: dict[str, Any]) -> dict[str, Any]:
    refresh_token = token.get("refresh_token")
    client_id = token.get("client_id")
    client_secret = token.get("client_secret")
    token_uri = token.get("token_uri", "https://oauth2.googleapis.com/token")
    if not refresh_token or not client_id or not client_secret:
        die("Gmail token missing refresh_token/client_id/client_secret")
    resp = requests.post(
        token_uri,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        die(f"Gmail token refresh failed: HTTP {resp.status_code} {resp.text[:300]}")
    refreshed = resp.json()
    token["token"] = refreshed["access_token"]
    if "refresh_token" in refreshed:
        token["refresh_token"] = refreshed["refresh_token"]
    if "expiry" in refreshed:
        token["expiry"] = refreshed["expiry"]
    save_token(token)
    return token


def gmail_get(path: str, token: dict[str, Any], retry: bool = True) -> dict[str, Any]:
    access_token = token.get("token")
    if not access_token:
        token = refresh_access_token(token)
        access_token = token.get("token")
    resp = requests.get(
        f"{GMAIL_BASE}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code == 401 and retry:
        token = refresh_access_token(token)
        return gmail_get(path, token, retry=False)
    if resp.status_code != 200:
        die(f"Gmail API request failed: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json()


def b64url_decode(data: str | None) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")


def extract_headers(payload: dict[str, Any]) -> dict[str, str]:
    headers = {}
    for h in payload.get("headers", []):
        name = h.get("name", "")
        value = h.get("value", "")
        if name:
            headers[name.lower()] = value
    return headers


def parse_sender(from_header: str) -> tuple[str, str]:
    from email.utils import parseaddr
    name, addr = parseaddr(from_header)
    return name or "", (addr or "").lower()


def walk_parts_for_bodies(part: dict[str, Any], html_parts: list[str], text_parts: list[str], attachments: list[dict[str, Any]]) -> None:
    mime = (part.get("mimeType") or "").lower()
    body = part.get("body", {}) or {}
    filename = part.get("filename") or ""
    attachment_id = body.get("attachmentId")
    data = body.get("data")

    if mime == "text/html" and data:
        html_parts.append(b64url_decode(data))
    elif mime == "text/plain" and data:
        text_parts.append(b64url_decode(data))
    elif filename and attachment_id:
        attachments.append({
            "name": filename,
            "contentType": mime or "application/octet-stream",
            "size": body.get("size", 0),
            "attachmentId": attachment_id,
        })

    for sub in part.get("parts", []) or []:
        walk_parts_for_bodies(sub, html_parts, text_parts, attachments)


def download_attachment(message_id: str, attachment: dict[str, Any], token: dict[str, Any], output_dir: Path) -> str:
    attachment_id = attachment["attachmentId"]
    data = gmail_get(f"/messages/{message_id}/attachments/{attachment_id}", token)
    raw = data.get("data")
    if not raw:
        die(f"Attachment {attachment['name']} had no data")
    msg_dir = output_dir / message_id
    msg_dir.mkdir(parents=True, exist_ok=True)
    file_path = msg_dir / attachment["name"]
    padded = raw + "=" * (-len(raw) % 4)
    file_path.write_bytes(base64.urlsafe_b64decode(padded.encode("utf-8")))
    return str(file_path)


def main() -> None:
    p = argparse.ArgumentParser(description="Read Gmail from trusted sender")
    p.add_argument("message_id")
    p.add_argument("--download-attachments", action="store_true")
    p.add_argument("--output-dir")
    args = p.parse_args()

    contacts = load_known_contacts()
    if not contacts:
        die("No known contacts configured")

    token = load_token()
    message = gmail_get(f"/messages/{args.message_id}?format=full", token)
    payload = message.get("payload", {}) or {}
    headers = extract_headers(payload)
    sender_name, sender_addr = parse_sender(headers.get("from", ""))

    if sender_addr not in contacts:
        print(json.dumps({
            "error": "Sender not approved",
            "sender": sender_addr,
            "message": "This Gmail message is from an unknown sender and cannot be read automatically"
        }), file=sys.stderr)
        raise SystemExit(1)

    html_parts: list[str] = []
    text_parts: list[str] = []
    attachments: list[dict[str, Any]] = []
    walk_parts_for_bodies(payload, html_parts, text_parts, attachments)

    downloaded_files: list[str] = []
    if args.download_attachments and attachments:
        out_dir = Path(args.output_dir) if args.output_dir else DEFAULT_ATTACHMENT_DIR
        for att in attachments:
            downloaded_files.append(download_attachment(args.message_id, att, token, out_dir))

    result = {
        "success": True,
        "message_id": args.message_id,
        "thread_id": message.get("threadId", ""),
        "subject": headers.get("subject", ""),
        "from": {"name": sender_name, "address": sender_addr},
        "received": headers.get("date", ""),
        "snippet": message.get("snippet", ""),
        "body": {
            "content": "\n\n".join(html_parts) if html_parts else "\n\n".join(text_parts),
            "type": "html" if html_parts else "text",
        },
        "has_attachments": bool(attachments),
        "attachments": [
            {k: v for k, v in att.items() if k != "attachmentId"}
            for att in attachments
        ],
        "downloaded_files": downloaded_files,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

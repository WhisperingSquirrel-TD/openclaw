#!/usr/bin/env python3
"""
Trusted Email Reader for OpenClaw
Reads full email bodies and downloads attachments from Microsoft Graph API
ONLY for emails from known/trusted contacts (no TOTP required)

Usage:
    python3 read_email.py <message_id> [--account assistant]

Security:
    - Checks sender against known-contacts.txt
    - Refuses to read emails from non-approved senders
    - Uses existing Microsoft token files (no new auth needed)

Output:
    JSON to stdout with email details
    Exit codes: 0=success, 1=sender not approved, 2=error
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import requests

# Paths
STATE_DIR = Path.home() / ".openclaw"
CONTACTS_FILE = STATE_DIR / "integrations/known-contacts.txt"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def load_known_contacts():
    """Load approved sender list"""
    if not CONTACTS_FILE.exists():
        return []
    lines = CONTACTS_FILE.read_text().splitlines()
    return [l.strip().lower() for l in lines if l.strip() and not l.strip().startswith("#")]


def load_token(account="assistant"):
    """Load existing Microsoft token"""
    token_path = STATE_DIR / f"integrations/microsoft/token-{account}.json"
    if not token_path.exists():
        print(json.dumps({"error": f"Token file not found: {token_path}"}), file=sys.stderr)
        sys.exit(2)
    
    try:
        with open(token_path) as f:
            data = json.load(f)
        
        # Handle both flat format and MSAL cache format
        if "AccessToken" in data:
            # MSAL cache format
            at_list = list(data.get("AccessToken", {}).values())
            if not at_list:
                print(json.dumps({"error": "No access token in MSAL cache"}), file=sys.stderr)
                sys.exit(2)
            return at_list[0]["secret"]
        else:
            # Flat format
            return data.get("access_token", "")
    except Exception as e:
        print(json.dumps({"error": f"Failed to load token: {e}"}), file=sys.stderr)
        sys.exit(2)


def get_email_details(message_id, access_token):
    """Fetch full email details from Graph API"""
    url = f"{GRAPH_BASE}/me/messages/{message_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text}"}), file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(json.dumps({"error": f"Failed to fetch email: {e}"}), file=sys.stderr)
        sys.exit(2)


def get_attachments(message_id, access_token):
    """Fetch attachment list from Graph API"""
    url = f"{GRAPH_BASE}/me/messages/{message_id}/attachments"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("value", [])
    except Exception as e:
        # Non-fatal - return empty list if attachments can't be fetched
        return []


def save_attachment(message_id, attachment_data, output_dir):
    """Save attachment to disk"""
    name = attachment_data.get("name", "attachment")
    content_bytes = attachment_data.get("contentBytes")
    
    if not content_bytes:
        return None
    
    # Create output directory
    msg_dir = output_dir / message_id
    msg_dir.mkdir(parents=True, exist_ok=True)
    
    # Decode and save
    import base64
    file_path = msg_dir / name
    file_path.write_bytes(base64.b64decode(content_bytes))
    return str(file_path)


def main():
    parser = argparse.ArgumentParser(description="Read email from trusted sender")
    parser.add_argument("message_id", help="Message ID to read")
    parser.add_argument("--account", default="assistant", help="Account name (default: assistant)")
    parser.add_argument("--download-attachments", action="store_true", help="Download attachments to workspace")
    parser.add_argument("--output-dir", help="Directory for attachments (default: ~/.openclaw/workspace/expense-attachments)")
    args = parser.parse_args()
    
    # Load approved senders
    known_contacts = load_known_contacts()
    if not known_contacts:
        print(json.dumps({"error": "No known contacts configured"}), file=sys.stderr)
        sys.exit(2)
    
    # Load token
    access_token = load_token(args.account)
    
    # Fetch email details
    email = get_email_details(args.message_id, access_token)
    
    # Extract sender email
    sender_addr = email.get("from", {}).get("emailAddress", {}).get("address", "").lower()
    
    # Security check: is sender approved?
    if sender_addr not in known_contacts:
        print(json.dumps({
            "error": "Sender not approved",
            "sender": sender_addr,
            "message": "This email is from an unknown sender and cannot be read without explicit approval"
        }), file=sys.stderr)
        sys.exit(1)
    
    # Extract body
    body_content = email.get("body", {}).get("content", "")
    body_type = email.get("body", {}).get("contentType", "text")
    
    # Check for attachments
    has_attachments = email.get("hasAttachments", False)
    attachment_list = []
    downloaded_files = []
    
    if has_attachments:
        attachments = get_attachments(args.message_id, access_token)
        for att in attachments:
            att_info = {
                "name": att.get("name"),
                "contentType": att.get("contentType"),
                "size": att.get("size")
            }
            attachment_list.append(att_info)
            
            # Download if requested
            if args.download_attachments:
                output_dir = Path(args.output_dir) if args.output_dir else STATE_DIR / "workspace/expense-attachments"
                file_path = save_attachment(args.message_id, att, output_dir)
                if file_path:
                    downloaded_files.append(file_path)
    
    # Build response
    result = {
        "success": True,
        "message_id": args.message_id,
        "subject": email.get("subject", ""),
        "from": {
            "name": email.get("from", {}).get("emailAddress", {}).get("name", ""),
            "address": sender_addr
        },
        "received": email.get("receivedDateTime", ""),
        "body": {
            "content": body_content,
            "type": body_type
        },
        "has_attachments": has_attachments,
        "attachments": attachment_list,
        "downloaded_files": downloaded_files
    }
    
    # Output JSON
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()

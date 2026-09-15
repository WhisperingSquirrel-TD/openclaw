#!/usr/bin/env python3
"""Read one exact external Microsoft Graph conversation through a dedicated read-only account.

This helper deliberately has no mailbox search, sender promotion, link following,
write, draft, or send capability. The account slug is intentionally separate from
the trusted reader account and must be provisioned independently.
"""
import argparse
import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import quote
import requests

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'
STATE_DIR = Path.home() / '.openclaw'
MAX_MESSAGES = 20
# The raw Graph bodies are bounded in memory before they are normalised. This
# protects the reader from an unexpectedly large exact conversation while the
# smaller serialized packet cap below protects the broker contract.
MAX_RAW_THREAD_BYTES = 4 * 1024 * 1024
MAX_BYTES = 64 * 1024
ACCOUNT = 'external-microsoft-read'
SELF_ADDRESSES = {
    'tom@stackstoneconsulting.co.uk',
    'tomdean1988@gmail.com',
    'assistant@stackstoneconsulting.co.uk',
}


def token(account):
    if account != ACCOUNT:
        raise RuntimeError('External reader account is fixed to the dedicated read-only account')
    # External-thread access is constrained by this helper's fixed exact-message
    # route, not by a second independently refreshed OAuth cache. The canonical
    # tom@ Microsoft token already has Mail.Read and is maintained by the live
    # mailbox poller. Prefer a dedicated cache if one is ever intentionally
    # provisioned, otherwise use that canonical read token; never search or write.
    candidates = [
        STATE_DIR / f'integrations/microsoft/token-{account}.json',
        STATE_DIR / 'integrations/microsoft/token-microsoft.json',
        STATE_DIR / 'integrations/microsoft/token.json',
    ]
    for p in candidates:
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        if 'AccessToken' in data:
            values = list(data['AccessToken'].values())
            if values and values[0].get('secret'):
                return values[0]['secret']
        value = data.get('access_token')
        if value:
            return value
    raise RuntimeError('Canonical Microsoft Mail.Read token is unavailable')


def graph_get(url, access, params=None):
    response = requests.get(url, params=params, headers={'Authorization': f'Bearer {access}'}, timeout=30)
    response.raise_for_status()
    return response.json()


def addresses(value):
    return [
        entry.get('emailAddress', {}).get('address', '').strip().lower()
        for entry in (value or [])
        if entry.get('emailAddress', {}).get('address', '').strip()
    ]


def authored_body(content):
    """Remove quoted history and presentation markup from an authored body."""
    text = str(content or '')
    patterns = (
        r'<div\b[^>]*\bid=["\'](?:x_)?divRplyFwdMsg["\'][^>]*>',
        r'<div\b[^>]*\bid=["\'](?:x_)?ms-outlook-mobile-body-separator-line["\'][^>]*>',
        r'<hr\b[^>]*>',
    )
    cuts = [match.start() for pattern in patterns for match in [re.search(pattern, text, re.IGNORECASE)] if match]
    if cuts:
        text = text[:min(cuts)]
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(?:div|p|tr|li|h[1-6])\s*>', '\n', text, flags=re.IGNORECASE)
    text = unescape(re.sub(r'<[^>]+>', '', text))
    text = re.sub(r'\n[ \t]*\n+', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def normalise_message(message):
    raw_body = str(message.get('body', {}).get('content', ''))
    sender = (message.get('from', {}).get('emailAddress', {}).get('address') or '').lower()
    is_draft = message.get('isDraft') is True
    authored_content = authored_body(raw_body)
    return {
        'message_id': message.get('id'),
        'conversation_id': message.get('conversationId'),
        'subject': message.get('subject', ''),
        'sender': sender,
        'to': addresses(message.get('toRecipients')),
        'cc': addresses(message.get('ccRecipients')),
        'received': message.get('receivedDateTime', ''),
        'sent': message.get('sentDateTime', ''),
        # The broker must distinguish a locally saved Outlook draft from an
        # actual sent outbound before applying duplicate-send suppression.
        'is_draft': is_draft,
        'status': 'draft' if is_draft else ('sent' if sender in SELF_ADDRESSES else 'inbound'),
        # Keep the source body available as untrusted input while exposing a
        # stable authored form for composition. Neither form is written here.
        'raw_body': raw_body,
        'authored_content': authored_content,
        'body': authored_content,
        'body_type': message.get('body', {}).get('contentType', 'text'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('message_id')
    parser.add_argument('--account', default=ACCOUNT)
    args = parser.parse_args()
    if args.account != ACCOUNT:
        raise RuntimeError('External reader account is fixed to the dedicated read-only account')
    if not args.message_id or len(args.message_id) > 512:
        raise RuntimeError('Message id is invalid')

    access = token(args.account)
    anchor = graph_get(f'{GRAPH_BASE}/me/messages/{quote(args.message_id, safe="")}', access)
    anchor_message = normalise_message(anchor)
    conversation_id = anchor_message.get('conversation_id')
    if not conversation_id:
        raise RuntimeError('Exact message has no conversation id; complete thread coverage is unavailable')

    # The conversation ID is returned by Graph for the exact anchor; escape it
    # before placing it in the bounded provider filter. Never accept a caller-
    # supplied conversation selector.
    filter_conversation_id = conversation_id.replace("'", "''")
    thread = graph_get(f'{GRAPH_BASE}/me/messages', access, params={
        '$filter': f"conversationId eq '{filter_conversation_id}'",
        '$top': str(MAX_MESSAGES + 1),
    })
    raw_messages = thread.get('value') or []
    if len(raw_messages) > MAX_MESSAGES:
        raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_MESSAGES}-message limit')
    messages = [normalise_message(message) for message in raw_messages]
    if not any(message.get('message_id') == anchor_message.get('message_id') for message in messages):
        messages.append(anchor_message)
    messages.sort(key=lambda message: (message.get('received') or message.get('sent') or '', message.get('message_id') or ''))
    if len(messages) > MAX_MESSAGES:
        raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_MESSAGES}-message limit')
    if any(message.get('conversation_id') not in {None, conversation_id} for message in messages):
        raise RuntimeError('Exact conversation response contained a message outside the anchor conversation')
    if not messages or not all(message.get('message_id') and message.get('sender') for message in messages):
        raise RuntimeError('Exact external conversation contains incomplete message identity')

    raw_bytes = sum(len(str(message['raw_body']).encode('utf-8')) for message in messages)
    if raw_bytes > MAX_RAW_THREAD_BYTES:
        raise RuntimeError(
            f'Exact conversation raw body exceeds the in-memory '
            f'{MAX_RAW_THREAD_BYTES}-byte resource ceiling'
        )
    total_bytes = sum(len(json.dumps(message, ensure_ascii=False).encode('utf-8')) for message in messages)
    if total_bytes > MAX_BYTES:
        raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_BYTES}-byte limit')
    print(json.dumps({'success': True, 'conversation_id': conversation_id, 'message_count': len(messages), 'messages': messages}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        sys.exit(2)

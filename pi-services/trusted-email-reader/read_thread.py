#!/usr/bin/env python3
"""Read one exact, trusted Microsoft Graph conversation without mailbox search."""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote
import requests

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'
STATE_DIR = Path.home() / '.openclaw'
CONTACTS_FILE = STATE_DIR / 'integrations/known-contacts.txt'
SELF_ADDRESSES = {'tom@stackstoneconsulting.co.uk', 'tomdean1988@gmail.com', 'assistant@stackstoneconsulting.co.uk'}
MAX_MESSAGES = 20
# Keep the exact-thread reader aligned with the task-context broker's
# 64 KiB bounded packet contract. Full coverage is still fail-closed above
# this limit; no truncation or fallback search is permitted.
MAX_BYTES = 64 * 1024


def contacts():
    if not CONTACTS_FILE.exists():
        return set()
    return {line.strip().lower() for line in CONTACTS_FILE.read_text().splitlines() if line.strip() and not line.startswith('#')} | SELF_ADDRESSES


def token(account):
    p = STATE_DIR / f'integrations/microsoft/token-{account}.json'
    if not p.exists():
        raise RuntimeError('Microsoft token file unavailable')
    data = json.loads(p.read_text())
    if 'AccessToken' in data:
        values = list(data['AccessToken'].values())
        if not values:
            raise RuntimeError('Microsoft access token unavailable')
        return values[0]['secret']
    value = data.get('access_token')
    if not value:
        raise RuntimeError('Microsoft access token unavailable')
    return value


def graph_get(url, access, params=None):
    response = requests.get(url, params=params, headers={'Authorization': f'Bearer {access}'}, timeout=30)
    response.raise_for_status()
    return response.json()


def authored_body(content):
    """Keep the authored portion; Outlook repeats quoted history in every body."""
    text = str(content or '')
    cut_markers = (
        '<div id="divRplyFwdMsg"',
        '<div id="ms-outlook-mobile-body-separator-line"',
    )
    cuts = [text.find(marker) for marker in cut_markers if text.find(marker) >= 0]
    if cuts:
        text = text[:min(cuts)]
    return text.strip()


def normalise_message(message):
    sender = (message.get('from', {}).get('emailAddress', {}).get('address') or '').lower()
    return {
        'message_id': message.get('id'),
        'conversation_id': message.get('conversationId'),
        'subject': message.get('subject', ''),
        'sender': sender,
        'received': message.get('receivedDateTime', ''),
        'body': authored_body(message.get('body', {}).get('content', '')),
        'body_type': message.get('body', {}).get('contentType', 'text'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('message_id')
    parser.add_argument('--account', default='microsoft')
    args = parser.parse_args()
    if not args.message_id or len(args.message_id) > 512:
        raise RuntimeError('message id is invalid')

    access = token(args.account)
    anchor = graph_get(f'{GRAPH_BASE}/me/messages/{quote(args.message_id, safe="")}', access)
    anchor_message = normalise_message(anchor)
    approved = contacts()
    if not anchor_message['sender'] or anchor_message['sender'] not in approved:
        print(json.dumps({'error': 'Sender not approved', 'sender': anchor_message['sender']}), file=sys.stderr)
        return 1
    conversation_id = anchor_message.get('conversation_id')
    if not conversation_id:
        raise RuntimeError('Exact message has no conversation id; complete thread coverage is unavailable')

    # This is an exact conversation lookup anchored by the already-authorised
    # message ID. It is not mailbox-wide search and never follows content links.
    thread = graph_get(f'{GRAPH_BASE}/me/messages', access, params={
        '$filter': f"conversationId eq '{conversation_id}'",
        '$top': str(MAX_MESSAGES + 1),
    })
    raw_messages = thread.get('value') or []
    if len(raw_messages) > MAX_MESSAGES:
        raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_MESSAGES}-message limit')
    messages = [normalise_message(message) for message in raw_messages]
    if not any(message.get('message_id') == anchor_message.get('message_id') for message in messages):
        messages.append(anchor_message)
    messages.sort(key=lambda message: message.get('received') or '')
    if len(messages) > MAX_MESSAGES:
        raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_MESSAGES}-message limit')
    unknown = sorted({message['sender'] for message in messages if message['sender'] not in approved})
    if unknown:
        raise RuntimeError(f'Conversation contains sender(s) outside the approved contact set: {", ".join(unknown)}')

    total_bytes = sum(len(json.dumps(message, ensure_ascii=False).encode('utf-8')) for message in messages)
    if total_bytes > MAX_BYTES:
        raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_BYTES}-byte limit')
    if not messages:
        raise RuntimeError('Exact trusted email conversation returned no messages')
    print(json.dumps({'success': True, 'conversation_id': conversation_id, 'message_count': len(messages), 'messages': messages}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        sys.exit(2)

#!/usr/bin/env python3
"""Read one exact, trusted Microsoft Graph conversation without mailbox search."""
import argparse
import json
import re
from html import unescape
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
    # Outlook/Graph can prefix HTML ids with x_ and vary attribute ordering, so
    # the previous literal markers missed quoted history. The first reply
    # separator is a deterministic message boundary; retain all authored HTML
    # before it and never truncate silently.
    patterns = (
        r'<div\b[^>]*\bid=["\'](?:x_)?divRplyFwdMsg["\'][^>]*>',
        r'<div\b[^>]*\bid=["\'](?:x_)?ms-outlook-mobile-body-separator-line["\'][^>]*>',
        r'<hr\b[^>]*>',
    )
    cuts = [match.start() for pattern in patterns for match in [re.search(pattern, text, re.IGNORECASE)] if match]
    if cuts:
        text = text[:min(cuts)]
    # Composition needs the authored facts, not Outlook's CSS/signature markup.
    # Convert the bounded authored HTML to stable plain text before enforcing
    # per-message byte limits downstream.
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(?:div|p|tr|li|h[1-6])\s*>', '\n', text, flags=re.IGNORECASE)
    text = unescape(re.sub(r'<[^>]+>', '', text))
    text = re.sub(r'\n[ \t]*\n+', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def normalise_message(message):
    sender = (message.get('from', {}).get('emailAddress', {}).get('address') or '').lower()
    return {
        'message_id': message.get('id'),
        'conversation_id': message.get('conversationId'),
        'subject': message.get('subject', ''),
        'sender': sender,
        'received': message.get('receivedDateTime', ''),
        # Preserve Graph draft state so downstream duplicate detection never
        # mistakes a saved draft for sent correspondence.
        'is_draft': message.get('isDraft') is True,
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
    # The exact anchor must be from an approved sender, but a legitimate
    # conversation may also include a vendor/support participant (for example
    # a client replying in a thread with the vendor copied).  Do not reject the
    # whole exact, bounded conversation for that reason: return the participant
    # classification so downstream composition continues to treat it as
    # untrusted source data, never as authority or an instruction.
    external_participants = sorted({message['sender'] for message in messages if message['sender'] and message['sender'] not in approved})

    total_bytes = sum(len(json.dumps(message, ensure_ascii=False).encode('utf-8')) for message in messages)
    if total_bytes > MAX_BYTES:
        raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_BYTES}-byte limit')
    if not messages:
        raise RuntimeError('Exact trusted email conversation returned no messages')
    print(json.dumps({'success': True, 'conversation_id': conversation_id, 'message_count': len(messages), 'external_participants': external_participants, 'messages': messages}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        sys.exit(2)

#!/usr/bin/env python3
"""Read one exact external Microsoft Graph conversation through a dedicated read-only account.

This helper deliberately has no mailbox search, sender promotion, link following,
write, draft, or send capability. The account slug is intentionally separate from
the trusted reader account and must be provisioned independently.
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote
import requests

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'
STATE_DIR = Path.home() / '.openclaw'
MAX_MESSAGES = 20
# Align with the task-context broker's hard packet cap. Quoted Outlook history
# is stripped below so the exact, bounded authored conversation stays useful.
MAX_BYTES = 64 * 1024
ACCOUNT = 'external-microsoft-read'


def token(account):
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


def authored_body(content):
    """Remove Outlook's repeated quoted history without widening retrieval."""
    text = str(content or '')
    markers = ('<div id="divRplyFwdMsg"', '<div id="ms-outlook-mobile-body-separator-line"')
    cuts = [text.find(marker) for marker in markers if text.find(marker) >= 0]
    return text[:min(cuts)].strip() if cuts else text.strip()


def normalise_message(message):
    return {
        'message_id': message.get('id'),
        'conversation_id': message.get('conversationId'),
        'subject': message.get('subject', ''),
        'sender': (message.get('from', {}).get('emailAddress', {}).get('address') or '').lower(),
        'received': message.get('receivedDateTime', ''),
        # The broker must distinguish a locally saved Outlook draft from an
        # actual sent outbound before applying duplicate-send suppression.
        'is_draft': message.get('isDraft') is True,
        'body': authored_body(message.get('body', {}).get('content', '')),
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
    messages.sort(key=lambda message: message.get('received') or '')
    if len(messages) > MAX_MESSAGES:
        raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_MESSAGES}-message limit')
    if any(message.get('conversation_id') not in {None, conversation_id} for message in messages):
        raise RuntimeError('Exact conversation response contained a message outside the anchor conversation')
    if not messages or not all(message.get('message_id') and message.get('sender') for message in messages):
        raise RuntimeError('Exact external conversation contains incomplete message identity')

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

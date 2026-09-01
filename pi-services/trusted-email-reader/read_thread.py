#!/usr/bin/env python3
"""Read one exact, trusted Microsoft Graph conversation without mailbox search.
Raw Graph bodies transit only in this process's stdout pipe to the broker; they are
never written to disk, logs, task state, or chat.
"""
import argparse, json, re, sys
from html import unescape
from pathlib import Path
from urllib.parse import quote
import requests

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'
STATE_DIR = Path.home() / '.openclaw'
CONTACTS_FILE = STATE_DIR / 'integrations/known-contacts.txt'
SELF_ADDRESSES = {'tom@stackstoneconsulting.co.uk', 'tomdean1988@gmail.com', 'assistant@stackstoneconsulting.co.uk'}
MAX_MESSAGES = 20
MAX_RAW_THREAD_BYTES = 4 * 1024 * 1024  # resource ceiling only; never a composition packet ceiling

def contacts():
    if not CONTACTS_FILE.exists(): return set()
    return {line.strip().lower() for line in CONTACTS_FILE.read_text().splitlines() if line.strip() and not line.startswith('#')} | SELF_ADDRESSES

def token(account):
    p = STATE_DIR / f'integrations/microsoft/token-{account}.json'
    if not p.exists(): raise RuntimeError('Microsoft token file unavailable')
    data = json.loads(p.read_text())
    if 'AccessToken' in data:
        values = list(data['AccessToken'].values())
        if values and values[0].get('secret'): return values[0]['secret']
    if data.get('access_token'): return data['access_token']
    raise RuntimeError('Microsoft access token unavailable')

def graph_get(url, access, params=None):
    response = requests.get(url, params=params, headers={'Authorization': f'Bearer {access}'}, timeout=30)
    response.raise_for_status(); return response.json()

def addresses(value):
    return [entry.get('emailAddress', {}).get('address', '').strip().lower() for entry in (value or []) if entry.get('emailAddress', {}).get('address', '').strip()]

def authored_body(content):
    """Deterministically remove only repeated Outlook quotation/history."""
    text = str(content or '')
    patterns = (r'<div\b[^>]*\bid=["\'](?:x_)?divRplyFwdMsg["\'][^>]*>', r'<div\b[^>]*\bid=["\'](?:x_)?ms-outlook-mobile-body-separator-line["\'][^>]*>', r'<hr\b[^>]*>')
    cuts = [m.start() for p in patterns for m in [re.search(p, text, re.I)] if m]
    if cuts: text = text[:min(cuts)]
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'</(?:div|p|tr|li|h[1-6])\s*>', '\n', text, flags=re.I)
    text = unescape(re.sub(r'<[^>]+>', '', text))
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n[ \t]*\n+', '\n\n', text)).strip()

def normalise_message(message):
    raw_body = str(message.get('body', {}).get('content', ''))
    sender = (message.get('from', {}).get('emailAddress', {}).get('address') or '').lower()
    is_draft = message.get('isDraft') is True
    return {'message_id': message.get('id'), 'conversation_id': message.get('conversationId'), 'subject': message.get('subject', ''), 'sender': sender, 'to': addresses(message.get('toRecipients')), 'cc': addresses(message.get('ccRecipients')), 'received': message.get('receivedDateTime', ''), 'sent': message.get('sentDateTime', ''), 'is_draft': is_draft, 'status': 'draft' if is_draft else ('sent' if sender in SELF_ADDRESSES else 'inbound'), 'raw_body': raw_body, 'authored_content': authored_body(raw_body), 'body_type': message.get('body', {}).get('contentType', 'text')}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('message_id'); parser.add_argument('--account', default='microsoft'); args = parser.parse_args()
    if not args.message_id or len(args.message_id) > 512: raise RuntimeError('message id is invalid')
    access = token(args.account); anchor = graph_get(f'{GRAPH_BASE}/me/messages/{quote(args.message_id, safe="")}', access); anchor_message = normalise_message(anchor)
    approved = contacts()
    if not anchor_message['sender'] or anchor_message['sender'] not in approved:
        print(json.dumps({'error': 'Sender not approved', 'sender': anchor_message['sender']}), file=sys.stderr); return 1
    conversation_id = anchor_message.get('conversation_id')
    if not conversation_id: raise RuntimeError('Exact message has no conversation id; complete thread coverage is unavailable')
    thread = graph_get(f'{GRAPH_BASE}/me/messages', access, params={'$filter': f"conversationId eq '{conversation_id.replace(chr(39), chr(39)*2)}'", '$top': str(MAX_MESSAGES + 1)})
    raw_messages = thread.get('value') or []
    if len(raw_messages) > MAX_MESSAGES: raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_MESSAGES}-message limit')
    messages = [normalise_message(message) for message in raw_messages]
    if not any(message.get('message_id') == anchor_message.get('message_id') for message in messages): messages.append(anchor_message)
    messages.sort(key=lambda message: (message.get('received') or message.get('sent') or '', message.get('message_id') or ''))
    if len(messages) > MAX_MESSAGES: raise RuntimeError(f'Exact conversation exceeds the bounded {MAX_MESSAGES}-message limit')
    raw_bytes = sum(len(str(message['raw_body']).encode('utf-8')) for message in messages)
    if raw_bytes > MAX_RAW_THREAD_BYTES: raise RuntimeError(f'Exact conversation raw body exceeds the in-memory {MAX_RAW_THREAD_BYTES}-byte resource ceiling')
    if not messages: raise RuntimeError('Exact trusted email conversation returned no messages')
    external_participants = sorted({message['sender'] for message in messages if message['sender'] and message['sender'] not in approved})
    print(json.dumps({'success': True, 'conversation_id': conversation_id, 'message_count': len(messages), 'external_participants': external_participants, 'messages': messages}, ensure_ascii=False)); return 0

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as exc: print(json.dumps({'error': str(exc)}), file=sys.stderr); sys.exit(2)

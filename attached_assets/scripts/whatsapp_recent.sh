#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="$HOME/.openclaw/workspace"
RECENT_MD="$WORKSPACE/WHATSAPP_RECENT.md"
RAW_JSONL="$HOME/.openclaw/credentials/whatsapp/watch-transcripts/whatsapp-watch-default.jsonl"
CONTACTS_MD="$WORKSPACE/contacts.md"
HOURS=48
MAX_LINES=400

if [ ! -f "$RAW_JSONL" ]; then
  cat > "$RECENT_MD" << EOF
# WhatsApp Recent (last ${HOURS}h)
_Updated: $(date '+%Y-%m-%d %H:%M') — raw transcript source missing. Full log: WHATSAPP_LOG.md_

_(no messages in the last ${HOURS} hours)_
EOF
  exit 0
fi

python3 - <<'PY' > "$RECENT_MD"
from __future__ import annotations
import json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

workspace = Path.home() / '.openclaw' / 'workspace'
raw_jsonl = Path.home() / '.openclaw' / 'credentials' / 'whatsapp' / 'watch-transcripts' / 'whatsapp-watch-default.jsonl'
contacts_md = workspace / 'contacts.md'
hours = 48
max_lines = 400
cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

def normalize_number(num: str | None) -> str | None:
    if not num:
        return None
    digits = re.sub(r'\D', '', num)
    if not digits:
        return None
    if digits.startswith('44'):
        return '+' + digits
    if digits.startswith('0'):
        return '+44' + digits[1:]
    if num.strip().startswith('+'):
        return '+' + digits
    return '+' + digits

def load_contact_map(path: Path) -> dict[str, str]:
    mapping = {}
    if not path.exists():
        return mapping
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line.startswith('- **'):
            continue
        m = re.match(r'- \*\*(.+?)\*\*.*?Mobile:\s*([^|]+)', line)
        if not m:
            continue
        name = m.group(1).strip()
        number = normalize_number(m.group(2).strip())
        if number:
            mapping[number] = name
    return mapping

def display_name_for_direct(obj: dict, contact_map: dict[str, str], inferred_names_by_number: dict[str, str]) -> str:
    sender_name = (obj.get('senderName') or '').strip()
    chat_name = (obj.get('chatName') or '').strip()
    sender_number = normalize_number(obj.get('senderNumber'))
    chat_number = normalize_number(chat_name if re.search(r'\d', chat_name) else None) or sender_number
    if obj.get('isFromMe'):
        if chat_number and chat_number in inferred_names_by_number:
            return inferred_names_by_number[chat_number]
        if chat_number and chat_number in contact_map:
            return contact_map[chat_number]
        if sender_number and sender_number in contact_map:
            return contact_map[sender_number]
        if chat_name and not re.fullmatch(r'[+\d\s]+', chat_name):
            return chat_name
        return chat_number or sender_name or 'Direct chat'
    if sender_name and sender_name != '---':
        return sender_name
    if sender_number and sender_number in contact_map:
        return contact_map[sender_number]
    if chat_number and chat_number in contact_map:
        return contact_map[chat_number]
    if chat_name and not re.fullmatch(r'[+\d\s]+', chat_name):
        return chat_name
    return sender_number or chat_number or 'Unknown'

def render_body(obj: dict) -> str:
    body = (obj.get('body') or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    media_type = obj.get('mediaType')
    quoted = (obj.get('quotedMessage') or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not body and media_type:
        if media_type.startswith('image/'):
            body = '<media:image>'
        elif media_type.startswith('video/'):
            body = '<media:video>'
        elif media_type.startswith('audio/'):
            body = '<media:audio>'
        else:
            body = f'<media:{media_type}>'
    body = body or '<empty>'
    if quoted:
        body = body + '\n> ' + quoted.replace('\n', '\n> ')
    return body

contact_map = load_contact_map(contacts_md)
inferred_names_by_number = {}
objs = []
for line in raw_jsonl.read_text(encoding='utf-8').splitlines():
    if not line.strip():
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue
    if obj.get('channel') != 'whatsapp':
        continue
    ts_raw = obj.get('timestamp')
    if not ts_raw:
        continue
    try:
        dt = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
    except Exception:
        continue
    if dt < cutoff:
        continue
    if obj.get('chatType') == 'direct' and not obj.get('isFromMe'):
        sender_name = (obj.get('senderName') or '').strip()
        sender_number = normalize_number(obj.get('senderNumber'))
        if sender_name and sender_name != '---' and sender_number:
            inferred_names_by_number[sender_number] = sender_name
    objs.append((obj, dt))

rendered = []
for obj, dt in objs:
    ts_local = dt.astimezone().strftime('%Y-%m-%d %H:%M')
    chat_type = obj.get('chatType')
    body = render_body(obj)
    if chat_type == 'group':
        group = (obj.get('chatName') or 'Unknown group').strip()
        sender = (obj.get('senderName') or '').strip()
        if obj.get('isFromMe'):
            sender = 'Me'
        elif not sender or sender == '---':
            sender = normalize_number(obj.get('senderNumber')) or 'Unknown'
        rendered.append(f'[{ts_local}] [{group}] {sender}: {body}')
    elif chat_type == 'direct':
        peer = display_name_for_direct(obj, contact_map, inferred_names_by_number)
        if obj.get('isFromMe'):
            rendered.append(f'[{ts_local}] Tom -> {peer}: {body}')
        else:
            rendered.append(f'[{ts_local}] {peer}: {body}')

lines = rendered[-max_lines:]
updated = datetime.now().strftime('%Y-%m-%d %H:%M')
print(f'# WhatsApp Recent (last {hours}h)')
print(f'_Updated: {updated} — showing last {hours} hours (max {max_lines} lines). Source: structured WhatsApp transcript stream; legacy full log: WHATSAPP_LOG.md_')
print()
if lines:
    print('\n'.join(lines))
else:
    print(f'_(no messages in the last {hours} hours)_')
PY

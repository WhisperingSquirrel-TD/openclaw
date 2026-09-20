#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="$HOME/.openclaw/workspace"
RECENT_MD="$WORKSPACE/WHATSAPP_RECENT.md"
WINDOW_JSON="$WORKSPACE/memory/whatsapp-recent-window.json"
RAW_DIR="$HOME/.openclaw/credentials/whatsapp/watch-transcripts"
CONTACTS_MD="$WORKSPACE/contacts.md"
# The approved whatsapp-check contract is a semantic 48-hour rolling window.
# Keep this value aligned with the generated header and window sidecar; do not
# widen routine checks to the legacy/full-log horizon.
HOURS=48
MAX_LINES=1200

mkdir -p "$WORKSPACE" "$(dirname "$WINDOW_JSON")"

write_incomplete_window() {
  local status="$1"
  local reason="$2"
  local generated_at
  local tmp
  generated_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  tmp="$(mktemp "${WINDOW_JSON}.tmp.XXXXXX")"
  if ! cat > "$tmp" << EOF
{
  "schema_version": 1,
  "window_hours": ${HOURS},
  "generated_at": "${generated_at}",
  "earliest_retained_source_timestamp": null,
  "latest_retained_source_timestamp": null,
  "retained_message_count": null,
  "source_message_count": null,
  "source_account_count": null,
  "source_parse_error_count": null,
  "truncated": null,
  "source_status": "${status}",
  "coverage_status": "incomplete",
  "coverage_complete": false,
  "coverage_reason": "${reason}"
}
EOF
  then
    rm -f "$tmp"
    return 1
  fi
  mv -f "$tmp" "$WINDOW_JSON"
}

write_incomplete_recent() {
  local status="$1"
  local tmp
  tmp="$(mktemp "${RECENT_MD}.tmp.XXXXXX")"
  if [ "$status" = "missing" ]; then
    cat > "$tmp" << EOF
# WhatsApp Recent (last ${HOURS}h)
_Updated: $(date '+%Y-%m-%d %H:%M') — raw transcript source missing. Full log: WHATSAPP_LOG.md_

_(coverage incomplete: source unavailable; message absence is not verified)_
EOF
  else
    cat > "$tmp" << EOF
# WhatsApp Recent (last ${HOURS}h)
_Updated: $(date '+%Y-%m-%d %H:%M') — raw transcript source could not be read or rendered. Full log: WHATSAPP_LOG.md_

_(coverage incomplete: source unavailable; message absence is not verified)_
EOF
  fi
  mv -f "$tmp" "$RECENT_MD"
}

if [ ! -d "$RAW_DIR" ] || ! compgen -G "$RAW_DIR/whatsapp-watch-*.jsonl" > /dev/null; then
  write_incomplete_window "missing" "raw_transcript_missing"
  write_incomplete_recent "missing"
  exit 0
fi

RECENT_TMP="$(mktemp "${RECENT_MD}.tmp.XXXXXX")"
if ! python3 - <<'PY' > "$RECENT_TMP"
from __future__ import annotations
import json, os, re, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

workspace = Path.home() / '.openclaw' / 'workspace'
raw_dir = Path.home() / '.openclaw' / 'credentials' / 'whatsapp' / 'watch-transcripts'
window_json = workspace / 'memory' / 'whatsapp-recent-window.json'
contacts_md = workspace / 'contacts.md'
# Keep the renderer and sidecar on the same approved semantic window as the
# shell header above.
hours = 48
max_lines = 1200
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
parse_errors = 0
raw_paths = sorted(raw_dir.glob('whatsapp-watch-*.jsonl'))
for raw_jsonl in raw_paths:
    try:
        source_lines = raw_jsonl.read_text(encoding='utf-8').splitlines()
    except Exception:
        parse_errors += 1
        continue
    for line in source_lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError('transcript record is not an object')
        except Exception:
            parse_errors += 1
            continue
        if obj.get('channel') != 'whatsapp':
            continue
        ts_raw = obj.get('timestamp')
        if not ts_raw:
            parse_errors += 1
            continue
        try:
            dt = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
        except Exception:
            parse_errors += 1
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
unrendered_records = 0
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
        rendered.append((f'[{ts_local}] [{group}] {sender}: {body}', dt))
    elif chat_type == 'direct':
        peer = display_name_for_direct(obj, contact_map, inferred_names_by_number)
        if obj.get('isFromMe'):
            rendered.append((f'[{ts_local}] Tom -> {peer}: {body}', dt))
        else:
            rendered.append((f'[{ts_local}] {peer}: {body}', dt))
    else:
        # A valid WhatsApp record with an unsupported chat type is still
        # source content. Do not silently call the resulting feed complete.
        unrendered_records += 1

# The recent file is a bounded mirror, not a per-thread summary. Keep every
# readable source record until the single global cap is reached, then retain
# the newest records and report incomplete coverage.
merged = sorted(rendered, key=lambda entry: entry[1])
retained = merged[-max_lines:]
lines = [line for line, _ in retained]
truncated = len(retained) < len(rendered)
coverage_reasons = []
if parse_errors:
    coverage_reasons.append('invalid_transcript_records')
if unrendered_records:
    coverage_reasons.append('unrendered_transcript_records')
if truncated:
    coverage_reasons.append('retention_limits')
coverage_complete = not coverage_reasons
source_status = 'ok' if not parse_errors and not unrendered_records else 'failed'
window_json.parent.mkdir(parents=True, exist_ok=True)
sidecar = {
    'schema_version': 1,
    'window_hours': hours,
    'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
    'source_account_count': len(raw_paths),
    'earliest_retained_source_timestamp': retained[0][1].astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z') if retained else None,
    'latest_retained_source_timestamp': retained[-1][1].astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z') if retained else None,
    'retained_message_count': len(retained),
    'source_message_count': len(objs),
    'source_parse_error_count': parse_errors,
    'truncated': truncated,
    'source_status': source_status,
    'coverage_status': 'complete' if coverage_complete else 'incomplete',
    'coverage_complete': coverage_complete,
    'coverage_reason': None if coverage_complete else ','.join(coverage_reasons),
}
with tempfile.NamedTemporaryFile(
    mode='w',
    encoding='utf-8',
    dir=window_json.parent,
    prefix=f'.{window_json.name}.tmp-',
    delete=False,
) as handle:
    json.dump(sidecar, handle, indent=2)
    handle.write('\n')
    sidecar_tmp = handle.name
os.replace(sidecar_tmp, window_json)
updated = datetime.now().strftime('%Y-%m-%d %H:%M')
print(f'# WhatsApp Recent (last {hours}h)')
print(f'_Updated: {updated} — showing last {hours} hours (max {max_lines} lines). Source: structured WhatsApp transcript streams; legacy full log: WHATSAPP_LOG.md_')
print()
warnings = []
if source_status != 'ok':
    warnings.append('⚠️ Coverage incomplete: the WhatsApp transcript source reported failures; message absence is not verified.')
if parse_errors:
    warnings.append(f'⚠️ Coverage incomplete: {parse_errors} transcript record(s) could not be parsed; displayed messages may be incomplete.')
if unrendered_records:
    warnings.append(f'⚠️ Coverage incomplete: {unrendered_records} valid transcript record(s) could not be rendered; displayed messages may be incomplete.')
if truncated:
    warnings.append(
        f'⚠️ Coverage incomplete: output was truncated by retention limits '
        f'({max_lines} total); displayed messages may be incomplete and message absence is not verified.'
    )
if warnings:
    print('\n'.join(warnings))
    print()
if lines:
    print('\n'.join(lines))
elif warnings:
    print('_(coverage incomplete: message absence is not verified)_')
else:
    print(f'_(no messages in the last {hours} hours)_')
PY
then
  rm -f "$RECENT_TMP"
  write_incomplete_window "failed" "raw_transcript_read_or_render_failed"
  write_incomplete_recent "failed"
  exit 1
fi
mv -f "$RECENT_TMP" "$RECENT_MD"

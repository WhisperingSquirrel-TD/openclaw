#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path('/home/tomdean88')
WORKSPACE = ROOT / '.openclaw' / 'workspace'
CODE_DIR = ROOT / 'openclaw' / 'pi-services' / 'expense-intake-watcher'
STATE_DIR = ROOT / '.openclaw' / 'runtime' / 'expense-intake-watcher'
STATE_FILE = STATE_DIR / 'state.json'
LOG_FILE = STATE_DIR / 'watcher.log'
EXPENSE_FILE = WORKSPACE / 'seer-expenses.md'
MS_READER = ROOT / 'openclaw' / 'pi-services' / 'trusted-email-reader' / 'read_email.py'
GMAIL_READER = ROOT / 'openclaw' / 'pi-services' / 'trusted-email-reader' / 'read_gmail.py'

INBOXES = [
    ('assistant', WORKSPACE / 'ASSISTANT_INBOX.md'),
    ('microsoft', WORKSPACE / 'MICROSOFT_INBOX.md'),
    ('gmail', WORKSPACE / 'GMAIL_INBOX.md'),
]

EXPENSE_PATTERNS = [
    re.compile(r'receipt from anthropic', re.I),
    re.compile(r'openai api invoice', re.I),
    re.compile(r'receipt from replit', re.I),
    re.compile(r'replit receipt', re.I),
    re.compile(r'your microsoft invoice', re.I),
]

@dataclass
class InboxEntry:
    account: str
    inbox_path: Path
    subject: str
    sender: str
    date_str: str
    message_id: str
    body_preview: str


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(f'[{ts}] {msg}\n')


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {'seen_message_ids': [], 'last_run': None}
    try:
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {'seen_message_ids': [], 'last_run': None}


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def parse_inbox_entries(account: str, path: Path) -> list[InboxEntry]:
    if not path.exists():
        return []
    text = path.read_text(encoding='utf-8')
    if '## Inbox' not in text:
        return []
    inbox_section = text.split('## Inbox', 1)[1]
    if '## Sent Items' in inbox_section:
        inbox_section = inbox_section.split('## Sent Items', 1)[0]
    chunks = [c.strip() for c in inbox_section.split('\n---\n') if c.strip()]
    out: list[InboxEntry] = []
    for chunk in chunks:
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        if len(lines) < 5:
            continue
        subject_match = re.match(r'\*\*(.+)\*\*', lines[0].strip())
        from_match = re.match(r'From: (.+) \| (.+)', lines[1].strip())
        mid_match = re.match(r'Message ID: (.+)', lines[2].strip())
        if not (subject_match and from_match and mid_match):
            # try more flexible scan
            subject = next((re.match(r'\*\*(.+)\*\*', ln).group(1) for ln in lines if re.match(r'\*\*(.+)\*\*', ln)), None)
            from_line = next((re.match(r'From: (.+) \| (.+)', ln) for ln in lines if re.match(r'From: (.+) \| (.+)', ln)), None)
            mid_line = next((re.match(r'Message ID: (.+)', ln) for ln in lines if re.match(r'Message ID: (.+)', ln)), None)
            if not (subject and from_line and mid_line):
                continue
            body_start_idx = lines.index(mid_line.string) + 1 if mid_line.string in lines else 3
            out.append(InboxEntry(account, path, subject, from_line.group(1), from_line.group(2), mid_line.group(1), ' '.join(lines[body_start_idx:])))
            continue
        out.append(InboxEntry(account, path, subject_match.group(1), from_match.group(1), from_match.group(2), mid_match.group(1), ' '.join(lines[3:])))
    return out


def is_expense(entry: InboxEntry) -> bool:
    subject = entry.subject.lower()
    preview = entry.body_preview.lower()
    return any(p.search(subject) or p.search(preview) for p in EXPENSE_PATTERNS)


def run_reader(entry: InboxEntry) -> dict[str, Any] | None:
    if entry.account == 'gmail':
        cmd = ['python3', str(GMAIL_READER), entry.message_id, '--download-attachments']
    elif entry.account == 'assistant':
        cmd = ['python3', str(MS_READER), entry.message_id, '--account', 'assistant', '--download-attachments']
    else:
        cmd = ['python3', str(MS_READER), entry.message_id, '--account', 'microsoft', '--download-attachments']
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f'reader failed for {entry.subject}: {proc.stderr[:300] or proc.stdout[:300]}')
        return None
    try:
        return json.loads(proc.stdout)
    except Exception as e:
        log(f'json parse failed for {entry.subject}: {e}')
        return None


def extract_date(raw: str) -> str:
    try:
        dt = parsedate_to_datetime(raw)
        return dt.date().isoformat()
    except Exception:
        m = re.search(r'(\d{4}-\d{2}-\d{2})', raw)
        return m.group(1) if m else raw[:10]


def text_from_reader(data: dict[str, Any]) -> str:
    body = data.get('body', {}).get('content', '') or ''
    # light html strip
    body = re.sub(r'<br\s*/?>', '\n', body, flags=re.I)
    body = re.sub(r'</p>|</div>|</tr>', '\n', body, flags=re.I)
    body = re.sub(r'<[^>]+>', ' ', body)
    body = body.replace('&nbsp;', ' ').replace('&amp;', '&')
    body = re.sub(r'\s+', ' ', body)
    return body


def extract_amounts(text: str) -> tuple[str | None, str | None]:
    # returns total, subtotal if found
    total = None
    subtotal = None
    patterns = [
        (r'Amount paid\s*([$£€][0-9]+(?:\.[0-9]{2})?)', 'total'),
        (r'Total\s*([$£€][0-9]+(?:\.[0-9]{2})?)', 'total'),
        (r'Here is your invoice [A-Z0-9-]+ for ([$£€][0-9]+(?:\.[0-9]{2})?)', 'total'),
        (r'Receipt from [A-Za-z ,]+\s*([$£€][0-9]+(?:\.[0-9]{2})?)', 'total'),
        (r'Subtotal\s*([$£€][0-9]+(?:\.[0-9]{2})?)', 'subtotal'),
    ]
    for pat, kind in patterns:
        m = re.search(pat, text, re.I)
        if m:
            if kind == 'total' and not total:
                total = m.group(1)
            if kind == 'subtotal' and not subtotal:
                subtotal = m.group(1)
    # fallback: take last currency amount as total if sensible
    if not total:
        amounts = re.findall(r'[$£€][0-9]+(?:\.[0-9]{2})?', text)
        if amounts:
            total = amounts[-1]
    return total, subtotal


def extract_refs(subject: str, text: str) -> dict[str, str | None]:
    receipt = None
    invoice = None
    m = re.search(r'#([0-9]{4}-[0-9]{4}-[0-9]{4})', subject)
    if m:
        receipt = m.group(1)
    if not receipt:
        m = re.search(r'Receipt(?: number)?\s*#?\s*([0-9]{4}-[0-9]{4}-[0-9]{4})', text, re.I)
        if m:
            receipt = m.group(1)
    m = re.search(r'Invoice(?: number)?\s*#?\s*([A-Z0-9-]+)', text, re.I)
    if m:
        invoice = m.group(1)
    else:
        m = re.search(r'OpenAI API Invoice\s*([A-Z0-9-]+)', subject, re.I)
        if m:
            invoice = m.group(1)
    return {'receipt': receipt, 'invoice': invoice}


def infer_vendor(subject: str, sender_addr: str, text: str) -> tuple[str, str]:
    s = (subject + ' ' + sender_addr + ' ' + text).lower()
    if 'anthropic' in s:
        return 'Anthropic', 'Anthropic Claude API credits'
    if 'openai' in s:
        return 'OpenAI', 'OpenAI API usage'
    if 'replit' in s:
        return 'Replit', 'Replit subscription / usage'
    if 'microsoft' in s:
        return 'Microsoft', 'Microsoft billing'
    return 'Unknown', subject


def already_logged(expense_md: str, refs: dict[str, str | None], subject: str) -> bool:
    needles = [r for r in refs.values() if r]
    needles.append(subject)
    return any(n in expense_md for n in needles)


def build_row(entry: InboxEntry, reader: dict[str, Any]) -> str | None:
    text = text_from_reader(reader)
    refs = extract_refs(entry.subject, text)
    vendor, item = infer_vendor(entry.subject, reader.get('from', {}).get('address', ''), text)
    total, subtotal = extract_amounts(text)
    received = extract_date(reader.get('received', '') or entry.date_str)
    amount = total or 'TBC'
    currency_hint = ' USD' if '$' in amount else ''
    notes = []
    notes.append(f"Out-of-pocket ({reader.get('from', {}).get('address', '') or entry.sender}).")
    if refs.get('receipt'):
        notes.append(f"Receipt #{refs['receipt']}.")
    if refs.get('invoice'):
        notes.append(f"Invoice #{refs['invoice']}.")
    if subtotal and total and subtotal != total:
        notes.append(f"Subtotal {subtotal}; total {total}.")
    dls = reader.get('downloaded_files') or []
    if dls:
        notes.append('Attachments: ' + ', '.join(Path(p).name for p in dls) + ' stored in expense-attachments.')
    return f"| {datetime.fromisoformat(received).strftime('%-d %b %Y')} | {item} | {vendor} | {amount}{currency_hint} | {' '.join(notes)} |"


def insert_row(row: str) -> bool:
    text = EXPENSE_FILE.read_text(encoding='utf-8')
    if row in text:
        return False
    marker = '\n## Domains\n'
    if marker not in text:
        log('Could not find Domains marker in expense file')
        return False
    new_text = text.replace(marker, row + '\n\n## Domains\n', 1)
    EXPENSE_FILE.write_text(new_text, encoding='utf-8')
    return True


def main() -> None:
    state = load_state()
    seen = set(state.get('seen_message_ids', []))
    expense_md = EXPENSE_FILE.read_text(encoding='utf-8') if EXPENSE_FILE.exists() else ''
    new_seen = set(seen)
    processed = 0
    logged = 0
    duplicates = 0
    blocked = 0

    for account, path in INBOXES:
        for entry in parse_inbox_entries(account, path):
            if entry.message_id in seen:
                continue
            if not is_expense(entry):
                new_seen.add(entry.message_id)
                continue
            processed += 1
            reader = run_reader(entry)
            if not reader:
                blocked += 1
                new_seen.add(entry.message_id)
                continue
            refs = extract_refs(entry.subject, text_from_reader(reader))
            if already_logged(expense_md, refs, entry.subject):
                duplicates += 1
                new_seen.add(entry.message_id)
                continue
            row = build_row(entry, reader)
            if row and insert_row(row):
                expense_md += '\n' + row
                logged += 1
                log(f'Logged expense from {account}: {entry.subject}')
            else:
                blocked += 1
            new_seen.add(entry.message_id)

    state['seen_message_ids'] = sorted(new_seen)
    state['last_run'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    state['last_summary'] = {'processed': processed, 'logged': logged, 'duplicates': duplicates, 'blocked': blocked}
    save_state(state)
    print(json.dumps(state['last_summary']))


if __name__ == '__main__':
    main()

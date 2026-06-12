#!/usr/bin/env python3
from __future__ import annotations

import hashlib
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
STATE_DIR = ROOT / '.openclaw' / 'runtime' / 'expense-intake-watcher'
STATE_FILE = STATE_DIR / 'state.json'
LOG_FILE = STATE_DIR / 'watcher.log'
EXPENSE_FILE = WORKSPACE / 'seer-expenses.md'
MONITORED_FILE = WORKSPACE / 'memory' / 'monitored-items-state.json'
MS_READER = ROOT / 'openclaw' / 'pi-services' / 'trusted-email-reader' / 'read_email.py'
GMAIL_READER = ROOT / 'openclaw' / 'pi-services' / 'trusted-email-reader' / 'read_gmail.py'
WHATSAPP_RECENT = WORKSPACE / 'WHATSAPP_RECENT.md'

EMAIL_SOURCES = [
    ('assistant', WORKSPACE / 'ASSISTANT_INBOX.md'),
    ('microsoft', WORKSPACE / 'MICROSOFT_INBOX.md'),
    ('gmail', WORKSPACE / 'GMAIL_INBOX.md'),
]

EMAIL_STRONG_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'receipt from anthropic',
        r'openai api invoice',
        r'your openai api account has been funded',
        r'receipt from replit',
        r'replit receipt',
        r'your microsoft invoice',
        r'order confirmation for startup huddle oxford',
        r'doxzoo - your order has been placed',
        r'doxzoo - order confirmation',
        r'\bobcn\b.*invoice',
    ]
]

KNOWN_EXPENSE_SENDERS = [
    'invoice+statements@mail.anthropic.com',
    'noreply@tm.openai.com',
    'noreply@billing.replit.com',
    'receipts+acct_',
    'invoice+statements+acct_',
    'microsoft-noreply@microsoft.com',
    'noreply@order.eventbrite.com',
    'hello@doxzoo.com',
]

WHATSAPP_STRONG_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'\b(receipt|paid|payment|refund|reimburse|reimburs|uber|taxi|train|bus|petrol|fuel|mileage|hotel|airbnb|expense|subscription|renewal)\b',
        r'[£$€]\s?\d',
    ]
]

WHATSAPP_BUSINESS_HINTS = [
    re.compile(p, re.I)
    for p in [
        r'\b(client|networking|receipt|parking|mileage|train|bus|uber|taxi|hotel|conference|croyde|stackstone|seer|pt)\b'
    ]
]

PREFERRED_CLOSURE_STATES = {
    'logged': 'expense_done',
    'duplicate': 'closed',
    'pending': 'blocked_pending_gate',
    'not_needed': 'not_needed',
}


@dataclass
class MailEntry:
    account: str
    section: str
    mailbox_path: Path
    subject: str
    party: str
    date_str: str
    message_id: str
    body_preview: str


@dataclass
class WhatsAppEntry:
    timestamp: str
    contact: str
    text: str
    raw_line: str
    group: str | None = None

    @property
    def key(self) -> str:
        digest = hashlib.sha1(f'{self.timestamp}|{self.group or "direct"}|{self.contact}|{self.text}'.encode('utf-8')).hexdigest()[:16]
        return f'whatsapp:{digest}'


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(f'[{ts}] {msg}\n')


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def load_state() -> dict[str, Any]:
    return load_json(
        STATE_FILE,
        {
            'scanned_non_candidates': [],
            'item_states': {},
            'last_run': None,
            'last_summary': {},
        },
    )


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_FILE, state)


def parse_mail_sections(account: str, path: Path) -> list[MailEntry]:
    if not path.exists():
        return []
    text = path.read_text(encoding='utf-8')
    entries: list[MailEntry] = []
    for section_name, header, next_header in [
        ('inbox', '## Inbox', '## Sent Items'),
        ('sent', '## Sent Items', None),
    ]:
        if header not in text:
            continue
        section = text.split(header, 1)[1]
        if next_header and next_header in section:
            section = section.split(next_header, 1)[0]
        chunks = [c.strip() for c in section.split('\n---\n') if c.strip()]
        for chunk in chunks:
            lines = [ln for ln in chunk.splitlines() if ln.strip()]
            subject = _match_value(lines, r'\*\*(.+)\*\*')
            if not subject:
                continue
            party_match = _match_groups(lines, r'(?:From|To): (.+) \| (.+)')
            mid = _match_value(lines, r'Message ID: (.+)')
            if not (party_match and mid):
                continue
            body_start_idx = 0
            for idx, line in enumerate(lines):
                if line.startswith('Internet Message ID:'):
                    body_start_idx = idx + 1
                    break
                if line.startswith('Message ID:'):
                    body_start_idx = idx + 1
            preview = ' '.join(lines[body_start_idx:])
            entries.append(MailEntry(account, section_name, path, subject, party_match[0], party_match[1], mid, preview))
    return entries


def _match_value(lines: list[str], pattern: str) -> str | None:
    regex = re.compile(pattern)
    for line in lines:
        m = regex.match(line.strip())
        if m:
            return m.group(1)
    return None


def _match_groups(lines: list[str], pattern: str) -> tuple[str, str] | None:
    regex = re.compile(pattern)
    for line in lines:
        m = regex.match(line.strip())
        if m:
            return m.group(1), m.group(2)
    return None


def mail_key(entry: MailEntry) -> str:
    return f'email:{entry.account}:{entry.section}:{entry.message_id}'


def is_email_candidate(entry: MailEntry) -> bool:
    hay = f'{entry.subject} {entry.party} {entry.body_preview}'.lower()
    subject = entry.subject.lower()
    party = entry.party.lower()

    # Sent items should only trigger when they clearly represent vendor receipts/orders
    # or Tom forwarding a vendor receipt into another mailbox for processing.
    if entry.section == 'sent':
        if not any(sender_fragment.lower() in hay for sender_fragment in KNOWN_EXPENSE_SENDERS):
            if not subject.startswith('fwd:'):
                return False

    if any(p.search(hay) for p in EMAIL_STRONG_PATTERNS):
        return True

    # Known vendor senders remain valid triggers, but generic internal invoice traffic does not.
    if any(sender_fragment.lower() in hay for sender_fragment in KNOWN_EXPENSE_SENDERS):
        if 'assistant@stackstoneconsulting.co.uk' in party and 'invoice inv-' in subject and not subject.startswith('fwd:'):
            return False
        return True

    return False


def run_reader(entry: MailEntry) -> dict[str, Any] | None:
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
    except Exception as exc:
        log(f'json parse failed for {entry.subject}: {exc}')
        return None


def text_from_reader(data: dict[str, Any]) -> str:
    body = data.get('body', {}).get('content', '') or ''
    body = re.sub(r'<br\s*/?>', '\n', body, flags=re.I)
    body = re.sub(r'</p>|</div>|</tr>', '\n', body, flags=re.I)
    body = re.sub(r'<[^>]+>', ' ', body)
    body = body.replace('&nbsp;', ' ').replace('&amp;', '&')
    body = re.sub(r'\s+', ' ', body)
    return body.strip()


def extract_date(raw: str) -> str:
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat()
    except Exception:
        m = re.search(r'(\d{4}-\d{2}-\d{2})', raw)
        return m.group(1) if m else datetime.now(timezone.utc).date().isoformat()


def pretty_date(iso_date: str) -> str:
    return datetime.fromisoformat(iso_date).strftime('%-d %b %Y')


def extract_amounts(text: str) -> tuple[str | None, str | None]:
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


def infer_vendor(subject: str, party: str, text: str) -> tuple[str, str]:
    s = f'{subject} {party} {text}'.lower()
    if 'anthropic' in s:
        return 'Anthropic', 'Anthropic Claude API credits'
    if 'openai' in s:
        if 'account funded' in s:
            return 'OpenAI', 'OpenAI API account funded'
        return 'OpenAI', 'OpenAI API usage'
    if 'replit' in s:
        return 'Replit', 'Replit subscription / usage'
    if 'microsoft' in s:
        return 'Microsoft', 'Microsoft billing'
    if 'eventbrite' in s or 'ticket' in s:
        return 'Eventbrite', 'Event / ticket order'
    if 'doxzoo' in s:
        return 'DoxZoo', 'Print order'
    return 'Unknown', subject


def currency_hint(amount: str) -> str:
    return ' USD' if '$' in amount else ''


def load_expense_text() -> str:
    return EXPENSE_FILE.read_text(encoding='utf-8') if EXPENSE_FILE.exists() else ''


def row_exists(expense_md: str, refs: dict[str, str | None], subject: str) -> bool:
    needles = [x for x in refs.values() if x]
    needles.append(subject)
    return any(n and n in expense_md for n in needles)


def insert_expense_row(row: str) -> bool:
    text = load_expense_text()
    if row in text:
        return False
    marker = '\n## Domains\n'
    if marker not in text:
        log('Could not find Domains marker in expense file')
        return False
    EXPENSE_FILE.write_text(text.replace(marker, row + '\n\n## Domains\n', 1), encoding='utf-8')
    return True


def ensure_pending_email_row(entry: MailEntry, blocker: str, refs: dict[str, str | None] | None = None) -> bool:
    refs = refs or extract_refs(entry.subject, entry.body_preview)
    expense_md = load_expense_text()
    if row_exists(expense_md, refs, entry.subject):
        return False
    vendor, item = infer_vendor(entry.subject, entry.party, entry.body_preview)
    iso_date = extract_date(entry.date_str)
    row = (
        f"| {pretty_date(iso_date)} | {item} | {vendor} | TBC | Pending expense signal from {entry.section} mirror. "
        f"Subject: `{entry.subject}`. Source account: {entry.account}. Blocker: {blocker} |"
    )
    return insert_expense_row(row)


def build_logged_row(entry: MailEntry, reader: dict[str, Any]) -> str:
    text = text_from_reader(reader)
    refs = extract_refs(entry.subject, text)
    vendor, item = infer_vendor(entry.subject, reader.get('from', {}).get('address', ''), text)
    total, subtotal = extract_amounts(text)
    received = extract_date(reader.get('received', '') or entry.date_str)
    amount = total or 'TBC'
    notes = [f"Out-of-pocket ({reader.get('from', {}).get('address', '') or entry.party})."]
    if refs.get('receipt'):
        notes.append(f"Receipt #{refs['receipt']}.")
    if refs.get('invoice'):
        notes.append(f"Invoice #{refs['invoice']}.")
    if subtotal and total and subtotal != total:
        notes.append(f"Subtotal {subtotal}; total {total}.")
    downloaded = reader.get('downloaded_files') or []
    if downloaded:
        notes.append('Attachments: ' + ', '.join(Path(p).name for p in downloaded) + ' stored in expense-attachments.')
    return f"| {pretty_date(received)} | {item} | {vendor} | {amount}{currency_hint(amount)} | {' '.join(notes)} |"


def load_monitored() -> dict[str, Any]:
    return load_json(
        MONITORED_FILE,
        {
            'last_updated': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'schema_version': 1,
            'purpose': 'Lightweight closure-state ledger for monitored inbound/sent operational items.',
            'notes': [],
            'closure_states': list(PREFERRED_CLOSURE_STATES.values()),
            'items': [],
        },
    )


def upsert_monitored(item_id: str, payload: dict[str, Any]) -> None:
    doc = load_monitored()
    items = doc.setdefault('items', [])
    for idx, item in enumerate(items):
        if item.get('id') == item_id:
            items[idx] = payload
            break
    else:
        items.append(payload)
    doc['last_updated'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    save_json(MONITORED_FILE, doc)


def email_monitored_payload(entry: MailEntry, closure_state: str, blocker: str | None, refs: dict[str, str | None] | None = None) -> dict[str, Any]:
    refs = refs or extract_refs(entry.subject, entry.body_preview)
    vendor, _ = infer_vendor(entry.subject, entry.party, entry.body_preview)
    return {
        'id': mail_key(entry),
        'surface': f'{entry.account}_{entry.section}',
        'entity': vendor,
        'thread_key': refs.get('invoice') or refs.get('receipt') or entry.subject[:120],
        'source_timestamp': entry.date_str,
        'seen_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'flags': ['EXPENSE'],
        'mode': 'watch',
        'closure_state': closure_state,
        'blocker': blocker,
        'evidence_refs': ['seer-expenses.md'],
        'resolved_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z') if closure_state in ('expense_done', 'closed', 'not_needed') else None,
    }


def parse_whatsapp_recent() -> list[WhatsAppEntry]:
    if not WHATSAPP_RECENT.exists():
        return []
    entries: list[WhatsAppEntry] = []
    for line in WHATSAPP_RECENT.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line.startswith('['):
            continue
        m = re.match(r'^\[(.*?)\]\s+(?:\[(.*?)\]\s+)?([^:]+):\s+(.*)$', line)
        if not m:
            continue
        ts, group, contact, text = m.groups()
        entries.append(WhatsAppEntry(timestamp=ts, group=group, contact=contact.strip(), text=text.strip(), raw_line=line))
    return entries


def is_whatsapp_candidate(entry: WhatsAppEntry) -> bool:
    hay = entry.text.lower()
    if not any(p.search(hay) for p in WHATSAPP_STRONG_PATTERNS):
        return False
    if re.search(r'\b(invoice generator|parking directly across)\b', hay):
        return False
    return any(p.search(hay) for p in WHATSAPP_BUSINESS_HINTS) or bool(re.search(r'[£$€]\s?\d', hay))


def ensure_pending_whatsapp_row(entry: WhatsAppEntry, blocker: str) -> bool:
    expense_md = load_expense_text()
    if entry.text in expense_md:
        return False
    iso_date = extract_date(entry.timestamp)
    row = (
        f"| {pretty_date(iso_date)} | WhatsApp expense signal | Unknown | TBC | Pending expense signal from WhatsApp. "
        f"Contact: {entry.contact}. Message: `{entry.text[:160]}`. Blocker: {blocker} |"
    )
    return insert_expense_row(row)


def whatsapp_monitored_payload(entry: WhatsAppEntry, closure_state: str, blocker: str | None) -> dict[str, Any]:
    return {
        'id': entry.key,
        'surface': 'whatsapp_recent',
        'entity': entry.contact,
        'thread_key': entry.contact,
        'source_timestamp': entry.timestamp,
        'seen_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'flags': ['EXPENSE'],
        'mode': 'watch',
        'closure_state': closure_state,
        'blocker': blocker,
        'evidence_refs': ['seer-expenses.md'],
        'resolved_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z') if closure_state in ('expense_done', 'closed', 'not_needed') else None,
    }


def mark_state(state: dict[str, Any], key: str, route: str, status: str, detail: str | None = None) -> None:
    state.setdefault('item_states', {})[key] = {
        'route': route,
        'status': status,
        'detail': detail,
        'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
    }


def process_email_entry(state: dict[str, Any], entry: MailEntry, summary: dict[str, int]) -> None:
    key = mail_key(entry)
    scanned = set(state.get('scanned_non_candidates', []))
    current = state.get('item_states', {}).get(key, {})
    if not is_email_candidate(entry):
        if key not in scanned:
            scanned.add(key)
            state['scanned_non_candidates'] = sorted(scanned)
        if current.get('status') != 'not_needed':
            mark_state(state, key, 'email', 'not_needed', 'No expense-shaped signal detected in mirror')
        return

    summary['candidates'] += 1
    refs = extract_refs(entry.subject, entry.body_preview)
    expense_md = load_expense_text()
    if row_exists(expense_md, refs, entry.subject):
        summary['duplicates'] += 1
        mark_state(state, key, 'email', 'duplicate', 'Already present in seer-expenses.md')
        upsert_monitored(key, email_monitored_payload(entry, 'closed', None, refs))
        return

    reader = run_reader(entry)
    if reader:
        row = build_logged_row(entry, reader)
        if insert_expense_row(row):
            summary['logged'] += 1
            mark_state(state, key, 'email', 'logged', 'Reader extraction succeeded')
            upsert_monitored(key, email_monitored_payload(entry, 'expense_done', None, extract_refs(entry.subject, text_from_reader(reader))))
            log(f'Logged expense from {entry.account}/{entry.section}: {entry.subject}')
            return
        summary['duplicates'] += 1
        mark_state(state, key, 'email', 'duplicate', 'Built row already existed or could not be inserted uniquely')
        upsert_monitored(key, email_monitored_payload(entry, 'closed', None, refs))
        return

    blocker = 'Trusted reader could not extract full body/attachments from this mirrored email yet'
    ensure_pending_email_row(entry, blocker, refs)
    mark_state(state, key, 'email', 'pending', blocker)
    upsert_monitored(key, email_monitored_payload(entry, 'blocked_pending_gate', blocker, refs))
    summary['pending'] += 1


def process_whatsapp_entry(state: dict[str, Any], entry: WhatsAppEntry, summary: dict[str, int]) -> None:
    key = entry.key
    scanned = set(state.get('scanned_non_candidates', []))
    if not is_whatsapp_candidate(entry):
        if key not in scanned:
            scanned.add(key)
            state['scanned_non_candidates'] = sorted(scanned)
        if state.get('item_states', {}).get(key, {}).get('status') != 'not_needed':
            mark_state(state, key, 'whatsapp', 'not_needed', 'No strong expense/business signal detected in WhatsApp recent feed')
        return

    summary['candidates'] += 1
    expense_md = load_expense_text()
    if entry.text in expense_md:
        summary['duplicates'] += 1
        mark_state(state, key, 'whatsapp', 'duplicate', 'Already represented in seer-expenses.md')
        upsert_monitored(key, whatsapp_monitored_payload(entry, 'closed', None))
        return

    blocker = 'WhatsApp expense signal needs business relevance / payment-source confirmation or richer evidence before full logging'
    ensure_pending_whatsapp_row(entry, blocker)
    mark_state(state, key, 'whatsapp', 'pending', blocker)
    upsert_monitored(key, whatsapp_monitored_payload(entry, 'blocked_pending_gate', blocker))
    summary['pending'] += 1


def main() -> None:
    state = load_state()
    summary = {
        'candidates': 0,
        'logged': 0,
        'duplicates': 0,
        'pending': 0,
        'not_needed': 0,
    }

    for account, path in EMAIL_SOURCES:
        for entry in parse_mail_sections(account, path):
            process_email_entry(state, entry, summary)

    for entry in parse_whatsapp_recent():
        process_whatsapp_entry(state, entry, summary)

    state['last_run'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    state['last_summary'] = summary
    save_state(state)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()

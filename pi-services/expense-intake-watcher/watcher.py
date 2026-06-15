#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path('/home/tomdean88')
WORKSPACE = ROOT / '.openclaw' / 'workspace'
CANONICAL_RUNTIME_NAME = 'inbound-watch-router'
LEGACY_RUNTIME_NAME = 'expense-intake-watcher'
CANONICAL_STATE_DIR = ROOT / '.openclaw' / 'runtime' / CANONICAL_RUNTIME_NAME
LEGACY_STATE_DIR = ROOT / '.openclaw' / 'runtime' / LEGACY_RUNTIME_NAME
STATE_FILE = CANONICAL_STATE_DIR / 'state.json'
LEGACY_STATE_FILE = LEGACY_STATE_DIR / 'state.json'
LOG_FILE = CANONICAL_STATE_DIR / 'watcher.log'
LEGACY_LOG_FILE = LEGACY_STATE_DIR / 'watcher.log'
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

ALERT_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'you have only \d+ days left to complete your application',
        r'job application',
        r'invitation to speak',
        r'speaking opportunity',
        r'bounce',
        r'unsubscribe',
        r'payment received',
        r'payment confirmation',
    ]
]

FOLLOW_UP_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'follow up',
        r'worth a chat',
        r'great to meet',
        r'get back to you',
        r'action required',
        r'next steps?',
        r'can we book',
        r'shall we book',
        r'available on',
    ]
]

CRM_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'croydemedical',
        r'marketsrecon',
        r'new orbit|neworbit',
        r'sjpp|sjp',
        r'crm oxford|chapman robinson moore',
        r'harken',
        r'pyramidlearning',
        r'roomsandrooms',
    ]
]

DIARY_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'accepted:',
        r'calendar invite',
        r'microsoft teams meeting',
        r'appointment with',
        r'eventbrite',
        r'available on',
        r'booked for',
        r'confirmed for',
        r'\b\d{1,2}:\d{2}\b',
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

WHATSAPP_PRIORITY_CONTACTS = {'lauren', 'andy', 'andrew', 'michael', 'george'}
WHATSAPP_NOISE_GROUP_HINTS = ['linkedin', 'pod', 'bootcamp', 'nephews', 'ragtag', 'boys', 'mum +', 'southern dean', 'tom, lauren, suz and andy', 'personal brands', 'networking', 'wine tasters', 'school of sailing', 'visibility', 'sailing']
WHATSAPP_GROUP_BROADCAST_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'https?://(?:www\.)?linkedin\.com/',
        r'https?://(?:www\.)?(?:facebook|share\.google)\.',
        r'\bgood morning(?:\s+everyone|\s+folks|\s+team)?\b',
        r'\bhappy monday\b',
        r'\bhope this is ok to share here\b',
        r'\bfor those who don\'t use the fb\b',
        r'^<media:(?:image|video|audio)>$',
    ]
]
WHATSAPP_PRIORITY_LOGISTICS_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'\bwhere (?:are|you at)\b',
        r'\beta\b',
        r'\bwhat time\b',
        r'\bwhen are we meeting\b',
        r'\bwhen we meeting\b',
        r'\bare you free\b',
        r'\bdo you have any plans\b',
        r'\brestaurant booked\b',
        r'\bin taxi\b',
        r'\bbooked\b',
        r'\bcan you\b',
        r'\bcould you\b',
        r'\bwould you\b',
        r'\blet me know\b',
    ]
]
WHATSAPP_PRIORITY_ALERT_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'\bcan you\b',
        r'\bcould you\b',
        r'\bwould you\b',
        r'\bdo you have any plans\b',
        r'\bare you free\b',
        r'\bwhat were you thinking\b',
        r'\bwhat time\b',
        r'\bwhere (?:are|you at)\b',
        r'\beta\b',
        r'\bwhen we meeting\b',
        r'\bwhen are we meeting\b',
        r'\blet\'s try and do that soon\b',
        r'\bin taxi\b',
        r'\brestaurant booked\b',
        r'\bbooked\b',
    ]
]
WHATSAPP_EXPENSE_BLOCKLIST_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'\bsweepstake\b',
        r'\bbuy-?in\b',
        r'\bcycling lot\b',
        r'\btrain from \w+',
        r'\breturn apparently\b',
        r'\bfirst train is the plan\b',
        r'\bin taxi\b',
        r'^£\s?\d+(?:\.\d{2})?$',
    ]
]
WHATSAPP_CRM_PATTERNS = [
    re.compile(p, re.I)
    for p in [r'croyde', r'harken', r'markets recon|market recons', r'neworbit|new orbit', r'crm oxford', r'rooms&rooms|roomsandrooms', r'wasim', r'santander', r'getloyl']
]
WHATSAPP_DIARY_PATTERNS = [
    re.compile(p, re.I)
    for p in [r'\b(today|tomorrow|tonight)\b', r'\b\d{1,2}:\d{2}\b', r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', r'\bthis evening\b', r'\bdo you have any plans\b', r'\bcoffee\b', r'\blunch\b', r'\bdinner\b']
]
WHATSAPP_FOLLOWUP_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r'\bcan you\b',
        r'\bwhat were you thinking\b',
        r'\bshall we\b',
        r'\bcould you\b',
        r'\bdo you have any plans\b',
        r'\bup to much\b',
        r'\bwhere you at\b',
        r'\beta\b',
        r'\bupdate\b',
        r'\blet me know\b',
        r'\bwhat time\b',
        r'\bare you free\b',
        r'\bcan we move\b',
    ]
]

WHATSAPP_LOW_SIGNAL_PHRASES = [
    re.compile(p, re.I)
    for p in [
        r'^ok[.!]*$',
        r'^thanks[.!]*$',
        r'^perfect[.!]*$',
        r'^great[.!]*$',
        r'^nice one[.!]*$',
        r'^see you then[.!]*$',
        r'^sounds good[.!]*$',
    ]
]
WHATSAPP_DIRECT_THREAD_LINK_WINDOW = timedelta(hours=6)
WHATSAPP_UNANSWERED_INBOUND_WINDOW = timedelta(hours=36)
WHATSAPP_HANGING_OUTBOUND_WINDOW = timedelta(hours=24)
WHATSAPP_STALE_THREAD_WINDOW = timedelta(days=7)
WHATSAPP_STALE_SURFACED_WINDOW = timedelta(hours=36)

PREFERRED_CLOSURE_STATES = {
    'logged': 'expense_done',
    'duplicate': 'closed',
    'pending': 'blocked_pending_gate',
    'not_needed': 'not_needed',
    'material_non_expense': 'surfaced',
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
    direct_thread_contact: str | None = None

    @property
    def key(self) -> str:
        digest = hashlib.sha1(f'{self.timestamp}|{self.group or "direct"}|{self.contact}|{self.text}'.encode('utf-8')).hexdigest()[:16]
        return f'whatsapp:{digest}'

    @property
    def timestamp_dt(self) -> datetime:
        return datetime.fromisoformat(self.timestamp).replace(tzinfo=timezone.utc)

    @property
    def is_direct(self) -> bool:
        return not self.group

    @property
    def is_me(self) -> bool:
        return self.contact.strip().lower() == 'me'

    @property
    def thread_key(self) -> str:
        if self.group:
            return f'group:{self.group.strip().lower()}'
        if self.is_me:
            return f'direct:{(self.direct_thread_contact or self.contact).strip().lower()}'
        return f'direct:{self.contact.strip().lower()}'


def runtime_dirs() -> list[Path]:
    return [CANONICAL_STATE_DIR, LEGACY_STATE_DIR]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    for path in [LOG_FILE, LEGACY_LOG_FILE]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
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


def default_state() -> dict[str, Any]:
    return {
        'runtime_name': CANONICAL_RUNTIME_NAME,
        'legacy_runtime_name': LEGACY_RUNTIME_NAME,
        'scanned_non_candidates': [],
        'item_states': {},
        'last_run': None,
        'last_summary': {},
    }


def load_state() -> dict[str, Any]:
    for candidate in [STATE_FILE, LEGACY_STATE_FILE]:
        if candidate.exists():
            state = load_json(candidate, default_state())
            if isinstance(state, dict):
                state.setdefault('runtime_name', CANONICAL_RUNTIME_NAME)
                state.setdefault('legacy_runtime_name', LEGACY_RUNTIME_NAME)
                state.setdefault('scanned_non_candidates', [])
                state.setdefault('item_states', {})
                state.setdefault('last_run', None)
                state.setdefault('last_summary', {})
                return state
    return default_state()


def save_state(state: dict[str, Any]) -> None:
    state['runtime_name'] = CANONICAL_RUNTIME_NAME
    state['legacy_runtime_name'] = LEGACY_RUNTIME_NAME
    save_json(STATE_FILE, state)
    save_json(LEGACY_STATE_FILE, state)


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


def classify_email_flags(entry: MailEntry) -> list[str]:
    hay = f'{entry.subject} {entry.party} {entry.body_preview}'.lower()
    flags: list[str] = []
    if is_email_candidate(entry):
        flags.append('EXPENSE')
    if any(p.search(hay) for p in ALERT_PATTERNS):
        flags.append('ALERT')
    if any(p.search(hay) for p in FOLLOW_UP_PATTERNS):
        flags.append('FOLLOW_UP')
    if any(p.search(hay) for p in CRM_PATTERNS):
        flags.append('CRM')
    if any(p.search(hay) for p in DIARY_PATTERNS):
        flags.append('DIARY')
    if entry.section == 'sent' or entry.subject.lower().startswith('re:') or entry.subject.lower().startswith('fw:') or entry.subject.lower().startswith('fwd:'):
        flags.append('OUTBOUND_CONTEXT')
    if not flags:
        flags.append('IGNORE')
    return sorted(set(flags))


def materially_important_email(entry: MailEntry, flags: list[str]) -> bool:
    flagset = set(flags)
    subject_l = entry.subject.lower()

    if 'l1-test' in subject_l or 'calendar test' in subject_l or 'repowatch' in subject_l:
        return False

    if entry.account == 'assistant' and entry.section == 'sent':
        if any(x in subject_l for x in ['junk mail', 'reservation', 'calendar test', 'l1-test', 'repowatch']):
            return False
        if subject_l.startswith('accepted:'):
            return any(x in subject_l for x in ['harken', 'service management system', 'speaking', 'startup huddle'])
        if 'ALERT' in flagset:
            return True
        if 'CRM' in flagset and any(x in subject_l for x in ['harken', 'neworbit', 'new orbit', 'croyde', 'markets recon', 'market recons', 'introduction', 'proposal', 'process mapping', 'support process mapping']):
            return True
        if 'FOLLOW_UP' in flagset and any(x in subject_l for x in ['great to meet', 'speaking opportunity', 'follow up']):
            return True
        return False

    if 'EXPENSE' in flagset or 'ALERT' in flagset:
        return True
    if 'CRM' in flagset:
        if any(x in subject_l for x in ['support process mapping', 'great to meet today - ai meeting follow up', 'great to meet today', 'harken', 'neworbit', 'new orbit', 'croyde', 'markets recon', 'market recons', 'introduction', 'proposal', 'process mapping']):
            return True
        return False
    if 'FOLLOW_UP' in flagset and 'OUTBOUND_CONTEXT' in flagset:
        return True
    if 'DIARY' in flagset and 'OUTBOUND_CONTEXT' in flagset and any(x in subject_l for x in ['accepted: service management system', 'accepted: harken', 'appointment with', 'startup huddle', 'speaking opportunity', 'microsoft teams meeting']):
        return True
    return False


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


def remove_monitored(item_id: str) -> None:
    doc = load_monitored()
    items = doc.get('items', [])
    filtered = [item for item in items if item.get('id') != item_id]
    if len(filtered) == len(items):
        return
    doc['items'] = filtered
    doc['last_updated'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    save_json(MONITORED_FILE, doc)


def email_monitored_payload(entry: MailEntry, closure_state: str, blocker: str | None, refs: dict[str, str | None] | None = None, flags: list[str] | None = None, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    refs = refs or extract_refs(entry.subject, entry.body_preview)
    vendor, _ = infer_vendor(entry.subject, entry.party, entry.body_preview)
    flags = flags or ['EXPENSE']
    evidence_refs = evidence_refs or ['seer-expenses.md']
    return {
        'id': mail_key(entry),
        'surface': f'{entry.account}_{entry.section}',
        'entity': vendor,
        'thread_key': refs.get('invoice') or refs.get('receipt') or entry.subject[:120],
        'source_timestamp': entry.date_str,
        'seen_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'flags': flags,
        'mode': 'watch',
        'closure_state': closure_state,
        'blocker': blocker,
        'evidence_refs': evidence_refs,
        'resolved_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z') if closure_state in ('expense_done', 'closed', 'not_needed', 'surfaced') else None,
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


def infer_direct_whatsapp_threads(entries: list[WhatsAppEntry]) -> list[WhatsAppEntry]:
    direct_indices = [idx for idx, entry in enumerate(entries) if entry.is_direct]
    for pos, idx in enumerate(direct_indices):
        entry = entries[idx]
        if not entry.is_me:
            entry.direct_thread_contact = entry.contact
            continue

        prev_contact = None
        prev_dt = None
        for prev_idx in reversed(direct_indices[:pos]):
            prev_entry = entries[prev_idx]
            if not prev_entry.is_me:
                prev_contact = prev_entry.contact
                prev_dt = prev_entry.timestamp_dt
                break

        next_contact = None
        next_dt = None
        for next_idx in direct_indices[pos + 1:]:
            next_entry = entries[next_idx]
            if not next_entry.is_me:
                next_contact = next_entry.contact
                next_dt = next_entry.timestamp_dt
                break

        chosen = None
        if prev_contact and next_contact and prev_contact.lower() == next_contact.lower():
            if prev_dt and next_dt and (entry.timestamp_dt - prev_dt) <= WHATSAPP_DIRECT_THREAD_LINK_WINDOW and (next_dt - entry.timestamp_dt) <= WHATSAPP_DIRECT_THREAD_LINK_WINDOW:
                chosen = prev_contact
        if not chosen and prev_contact and prev_dt and (entry.timestamp_dt - prev_dt) <= WHATSAPP_DIRECT_THREAD_LINK_WINDOW:
            chosen = prev_contact
        if not chosen and next_contact and next_dt and (next_dt - entry.timestamp_dt) <= WHATSAPP_DIRECT_THREAD_LINK_WINDOW:
            chosen = next_contact
        entry.direct_thread_contact = chosen
    return entries


def is_whatsapp_group_broadcast_noise(entry: WhatsAppEntry) -> bool:
    if not entry.group:
        return False
    group_l = (entry.group or '').lower()
    text = entry.text.strip()
    text_l = text.lower()
    if any(h in group_l for h in WHATSAPP_NOISE_GROUP_HINTS):
        if any(p.search(text) for p in WHATSAPP_GROUP_BROADCAST_PATTERNS):
            return True
        if text.startswith('http'):
            return True
    return False



def is_priority_direct_actionable(entry: WhatsAppEntry) -> bool:
    if not entry.is_direct or entry.is_me:
        return False
    if entry.contact.strip().lower() not in WHATSAPP_PRIORITY_CONTACTS:
        return True
    text = entry.text.strip()
    if not text or text.startswith('<media:'):
        return False
    if any(p.search(text) for p in WHATSAPP_PRIORITY_LOGISTICS_PATTERNS):
        return True
    if '?' in text and len(text) >= 12:
        return True
    return False



def classify_whatsapp_flags(entry: WhatsAppEntry) -> list[str]:
    hay = entry.text.lower()
    contact = entry.contact.lower()
    group_l = (entry.group or '').lower()
    is_direct = not entry.group
    flags: list[str] = []

    if any(p.search(entry.text.strip()) for p in WHATSAPP_LOW_SIGNAL_PHRASES):
        return ['IGNORE']

    if is_whatsapp_group_broadcast_noise(entry):
        return ['IGNORE']

    if is_whatsapp_candidate(entry):
        flags.append('EXPENSE')

    if any(name in contact for name in WHATSAPP_PRIORITY_CONTACTS) and contact != 'me' and is_direct:
        if is_priority_direct_actionable(entry) and any(p.search(hay) for p in WHATSAPP_PRIORITY_ALERT_PATTERNS):
            flags.append('ALERT')

    if any(p.search(hay) for p in WHATSAPP_CRM_PATTERNS):
        flags.append('CRM')

    if is_direct and is_priority_direct_actionable(entry) and any(p.search(hay) for p in WHATSAPP_DIARY_PATTERNS):
        flags.append('DIARY')

    if is_direct and is_priority_direct_actionable(entry) and any(p.search(hay) for p in WHATSAPP_FOLLOWUP_PATTERNS):
        flags.append('FOLLOW_UP')

    if entry.group or contact == 'me':
        flags.append('OUTBOUND_CONTEXT')

    if entry.group and any(h in group_l for h in WHATSAPP_NOISE_GROUP_HINTS) and 'EXPENSE' not in flags and 'CRM' not in flags:
        flags = ['IGNORE']

    if contact == 'me' and 'EXPENSE' not in flags and 'CRM' not in flags:
        flags = ['IGNORE']

    if not flags:
        flags.append('IGNORE')
    return sorted(set(flags))


def materially_important_whatsapp(entry: WhatsAppEntry, flags: list[str]) -> bool:
    flagset = set(flags)
    contact_l = entry.contact.lower()
    group_l = (entry.group or '').lower()

    if 'IGNORE' in flagset:
        return False
    if 'EXPENSE' in flagset:
        return True
    if entry.group:
        if any(h in group_l for h in WHATSAPP_NOISE_GROUP_HINTS) and 'CRM' not in flagset and 'EXPENSE' not in flagset:
            return False
        return 'CRM' in flagset or 'EXPENSE' in flagset
    if contact_l == 'me':
        return False
    if 'CRM' in flagset:
        return True
    if 'ALERT' in flagset:
        return True
    if 'FOLLOW_UP' in flagset:
        return True
    if 'DIARY' in flagset:
        return True
    return False


def is_whatsapp_candidate(entry: WhatsAppEntry) -> bool:
    hay = entry.text.lower()
    group_l = (entry.group or '').lower()
    if not any(p.search(hay) for p in WHATSAPP_STRONG_PATTERNS):
        return False
    if re.search(r'\b(invoice generator|parking directly across)\b', hay):
        return False
    if any(p.search(entry.text) for p in WHATSAPP_EXPENSE_BLOCKLIST_PATTERNS):
        return False
    if entry.group and any(h in group_l for h in WHATSAPP_NOISE_GROUP_HINTS):
        return False
    if entry.is_direct and entry.contact.lower() in WHATSAPP_PRIORITY_CONTACTS:
        if not re.search(r'\b(receipt|paid|payment|refund|reimburse|reimburs|subscription|renewal)\b', hay):
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


def whatsapp_monitored_payload(entry: WhatsAppEntry, closure_state: str, blocker: str | None, flags: list[str] | None = None, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    return {
        'id': entry.key,
        'surface': 'whatsapp_recent',
        'entity': entry.direct_thread_contact or entry.contact,
        'thread_key': entry.thread_key,
        'source_timestamp': entry.timestamp,
        'seen_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'flags': flags or ['EXPENSE'],
        'mode': 'watch',
        'closure_state': closure_state,
        'blocker': blocker,
        'evidence_refs': evidence_refs or ['seer-expenses.md'],
        'resolved_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z') if closure_state in ('expense_done', 'closed', 'not_needed', 'surfaced') else None,
    }


def mark_state(state: dict[str, Any], key: str, route: str, status: str, detail: str | None = None) -> None:
    state.setdefault('item_states', {})[key] = {
        'route': route,
        'status': status,
        'detail': detail,
        'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
    }


def latest_thread_entry(entries: list[WhatsAppEntry]) -> WhatsAppEntry | None:
    return entries[-1] if entries else None


def outbound_follow_up_signal(entry: WhatsAppEntry) -> bool:
    if not entry.is_direct or not entry.is_me:
        return False
    text = entry.text.strip()
    if not text or text.startswith('<media:'):
        return False
    if '?' in text:
        return True
    return any(p.search(text.lower()) for p in WHATSAPP_FOLLOWUP_PATTERNS)


def prune_whatsapp_artifacts(entries: list[WhatsAppEntry]) -> None:
    live_keys = {entry.key for entry in entries}
    live_direct_thread_keys = {entry.thread_key for entry in entries if entry.is_direct and (not entry.is_me or entry.direct_thread_contact)}
    live_actionable_keys = {
        entry.key for entry in entries
        if 'EXPENSE' in classify_whatsapp_flags(entry) or materially_important_whatsapp(entry, classify_whatsapp_flags(entry))
    }
    live_expense_texts = {entry.text for entry in entries if 'EXPENSE' in classify_whatsapp_flags(entry)}

    doc = load_monitored()
    changed = False
    filtered_items = []
    now = datetime.now(timezone.utc)
    for item in doc.get('items', []):
        item_id = item.get('id', '')
        if not item_id.startswith('whatsapp:'):
            filtered_items.append(item)
            continue

        closure_state = item.get('closure_state')
        thread_key = item.get('thread_key')
        entity = str(item.get('entity', '')).lower()
        blocker = (item.get('blocker') or '').lower()
        source_ts = str(item.get('source_timestamp') or '')
        stale_source = False
        try:
            stale_source = datetime.fromisoformat(source_ts).replace(tzinfo=timezone.utc) < now - WHATSAPP_STALE_SURFACED_WINDOW
        except Exception:
            stale_source = False

        legacy_blocked_expense = closure_state == 'blocked_pending_gate' and ('expense signal needs business relevance' in blocker)
        stale_surfaced_nonlive = closure_state == 'surfaced' and thread_key and thread_key not in live_direct_thread_keys and stale_source
        stale_surfaced_live_nonactionable = closure_state == 'surfaced' and item_id in live_keys and item_id not in live_actionable_keys and stale_source
        noisy_priority_item = closure_state == 'surfaced' and entity in WHATSAPP_PRIORITY_CONTACTS and item_id not in live_actionable_keys
        no_longer_actionable_live_item = item_id in live_keys and item_id not in live_actionable_keys and closure_state in {'surfaced', 'blocked_pending_gate', 'closed'}

        if legacy_blocked_expense or stale_surfaced_nonlive or stale_surfaced_live_nonactionable or noisy_priority_item or no_longer_actionable_live_item:
            changed = True
            continue
        filtered_items.append(item)

    if changed:
        doc['items'] = filtered_items
        doc['last_updated'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        save_json(MONITORED_FILE, doc)

    expense_text = load_expense_text()
    expense_lines = expense_text.splitlines()
    filtered_lines: list[str] = []
    expense_changed = False
    for line in expense_lines:
        if 'Pending expense signal from WhatsApp.' not in line:
            filtered_lines.append(line)
            continue
        msg_match = re.search(r'Message: `([^`]+)`', line)
        message_preview = msg_match.group(1) if msg_match else None
        if not message_preview:
            filtered_lines.append(line)
            continue
        if message_preview not in live_expense_texts:
            expense_changed = True
            continue
        filtered_lines.append(line)
    if expense_changed:
        EXPENSE_FILE.write_text('\n'.join(filtered_lines) + '\n', encoding='utf-8')


def process_whatsapp_threads(state: dict[str, Any], entries: list[WhatsAppEntry], summary: dict[str, int]) -> None:
    threads: dict[str, list[WhatsAppEntry]] = {}
    for entry in entries:
        if not entry.is_direct:
            continue
        if entry.is_me and not entry.direct_thread_contact:
            continue
        threads.setdefault(entry.thread_key, []).append(entry)

    now = datetime.now(timezone.utc)
    for thread_key, thread_entries in threads.items():
        latest = latest_thread_entry(thread_entries)
        if not latest or latest.timestamp_dt < now - WHATSAPP_STALE_THREAD_WINDOW:
            continue

        latest_inbound = next((entry for entry in reversed(thread_entries) if not entry.is_me), None)
        latest_outbound = next((entry for entry in reversed(thread_entries) if entry.is_me), None)
        latest_actionable_inbound = next(
            (
                entry for entry in reversed(thread_entries)
                if not entry.is_me and materially_important_whatsapp(entry, classify_whatsapp_flags(entry))
            ),
            None,
        )

        if latest_actionable_inbound and latest is latest_actionable_inbound:
            if latest.timestamp_dt >= now - WHATSAPP_UNANSWERED_INBOUND_WINDOW:
                flags = classify_whatsapp_flags(latest)
                if 'EXPENSE' not in flags:
                    summary['material_non_expense'] += 1
                    upsert_monitored(
                        latest.key,
                        whatsapp_monitored_payload(
                            latest,
                            'surfaced',
                            'Latest actionable inbound in direct thread has no later visible Me: reply yet',
                            flags=sorted(set(flags + ['OUTBOUND_CONTEXT'])),
                            evidence_refs=['WHATSAPP_RECENT.md', 'memory/monitored-items-state.json'],
                        ),
                    )
                    mark_state(state, latest.key, 'whatsapp', 'surfaced', 'Direct thread still waiting on Tom reply')
            continue

        if latest and latest.is_me and outbound_follow_up_signal(latest):
            has_later_inbound = any((not entry.is_me and entry.timestamp_dt > latest.timestamp_dt) for entry in thread_entries)
            if not has_later_inbound and latest.timestamp_dt >= now - WHATSAPP_HANGING_OUTBOUND_WINDOW:
                summary['material_non_expense'] += 1
                upsert_monitored(
                    latest.key,
                    whatsapp_monitored_payload(
                        latest,
                        'surfaced',
                        'Tom sent the latest direct follow-up/chase and there is no later visible reply yet',
                        flags=['FOLLOW_UP', 'OUTBOUND_CONTEXT'],
                        evidence_refs=['WHATSAPP_RECENT.md', 'memory/monitored-items-state.json'],
                    ),
                )
                mark_state(state, latest.key, 'whatsapp', 'surfaced', 'Direct thread may need chase tracking')


def process_email_entry(state: dict[str, Any], entry: MailEntry, summary: dict[str, int]) -> None:
    key = mail_key(entry)
    scanned = set(state.get('scanned_non_candidates', []))
    current = state.get('item_states', {}).get(key, {})
    flags = classify_email_flags(entry)

    summary['reviewed'] += 1
    mark_state(state, key, 'email', 'reviewed', ','.join(flags))

    if 'EXPENSE' not in flags:
        if materially_important_email(entry, flags):
            material_key = f"{entry.account}:{entry.section}:{tuple(flags)}:{entry.subject.strip().lower()[:160]}"
            seen_material = set(summary.setdefault('_seen_material_keys', []))
            if material_key not in seen_material:
                summary['material_non_expense'] += 1
                seen_material.add(material_key)
                summary['_seen_material_keys'] = sorted(seen_material)
            upsert_monitored(
                key,
                email_monitored_payload(
                    entry,
                    'surfaced',
                    None,
                    flags=flags,
                    evidence_refs=['memory/monitored-items-state.json'],
                ),
            )
        else:
            existing = load_monitored()
            items = existing.get('items', [])
            filtered = [i for i in items if i.get('id') != key]
            if len(filtered) != len(items):
                existing['items'] = filtered
                existing['last_updated'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                save_json(MONITORED_FILE, existing)
            summary['not_needed'] += 1
            if key not in scanned:
                scanned.add(key)
                state['scanned_non_candidates'] = sorted(scanned)
            if current.get('status') != 'not_needed':
                mark_state(state, key, 'email', 'not_needed', 'No routed signal detected in mirror')
        return

    summary['expense_candidates'] += 1
    refs = extract_refs(entry.subject, entry.body_preview)
    expense_md = load_expense_text()
    if row_exists(expense_md, refs, entry.subject):
        summary['duplicates'] += 1
        mark_state(state, key, 'email', 'duplicate', 'Already present in seer-expenses.md')
        upsert_monitored(key, email_monitored_payload(entry, 'closed', None, refs, flags=flags))
        return

    reader = run_reader(entry)
    if reader:
        row = build_logged_row(entry, reader)
        if insert_expense_row(row):
            summary['logged'] += 1
            mark_state(state, key, 'email', 'logged', 'Reader extraction succeeded')
            upsert_monitored(key, email_monitored_payload(entry, 'expense_done', None, extract_refs(entry.subject, text_from_reader(reader)), flags=flags))
            log(f'Logged expense from {entry.account}/{entry.section}: {entry.subject}')
            return
        summary['duplicates'] += 1
        mark_state(state, key, 'email', 'duplicate', 'Built row already existed or could not be inserted uniquely')
        upsert_monitored(key, email_monitored_payload(entry, 'closed', None, refs, flags=flags))
        return

    blocker = 'Trusted reader could not extract full body/attachments from this mirrored email yet'
    ensure_pending_email_row(entry, blocker, refs)
    mark_state(state, key, 'email', 'pending', blocker)
    upsert_monitored(key, email_monitored_payload(entry, 'blocked_pending_gate', blocker, refs, flags=flags))
    summary['pending'] += 1


def process_whatsapp_entry(state: dict[str, Any], entry: WhatsAppEntry, summary: dict[str, int]) -> None:
    key = entry.key
    scanned = set(state.get('scanned_non_candidates', []))
    flags = classify_whatsapp_flags(entry)
    mark_state(state, key, 'whatsapp', 'reviewed', ','.join(flags))

    if 'EXPENSE' not in flags:
        if entry.is_direct and (not entry.group) and (not entry.is_me or entry.direct_thread_contact):
            remove_monitored(key)
            if key not in scanned:
                scanned.add(key)
                state['scanned_non_candidates'] = sorted(scanned)
            summary['not_needed'] += 1
            if state.get('item_states', {}).get(key, {}).get('status') != 'not_needed':
                mark_state(state, key, 'whatsapp', 'not_needed', 'Direct-thread non-expense signals are reconciled at thread level with Me: context')
            return
        if materially_important_whatsapp(entry, flags):
            summary['material_non_expense'] += 1
            upsert_monitored(key, whatsapp_monitored_payload(entry, 'surfaced', None, flags=flags, evidence_refs=['memory/monitored-items-state.json']))
        else:
            if key not in scanned:
                scanned.add(key)
                state['scanned_non_candidates'] = sorted(scanned)
            summary['not_needed'] += 1
            if state.get('item_states', {}).get(key, {}).get('status') != 'not_needed':
                mark_state(state, key, 'whatsapp', 'not_needed', 'No strong routed signal detected in WhatsApp recent feed')
        return

    summary['expense_candidates'] += 1
    expense_md = load_expense_text()
    if entry.text in expense_md:
        summary['duplicates'] += 1
        mark_state(state, key, 'whatsapp', 'duplicate', 'Already represented in seer-expenses.md')
        upsert_monitored(key, whatsapp_monitored_payload(entry, 'closed', None, flags=flags))
        return

    blocker = 'WhatsApp expense signal needs business relevance / payment-source confirmation or richer evidence before full logging'
    ensure_pending_whatsapp_row(entry, blocker)
    mark_state(state, key, 'whatsapp', 'pending', blocker)
    upsert_monitored(key, whatsapp_monitored_payload(entry, 'blocked_pending_gate', blocker, flags=flags))
    summary['pending'] += 1


def main() -> None:
    state = load_state()
    summary = {
        'reviewed': 0,
        'expense_candidates': 0,
        'logged': 0,
        'duplicates': 0,
        'pending': 0,
        'material_non_expense': 0,
        'not_needed': 0,
        '_seen_material_keys': [],
    }

    for account, path in EMAIL_SOURCES:
        for entry in parse_mail_sections(account, path):
            process_email_entry(state, entry, summary)

    whatsapp_entries = infer_direct_whatsapp_threads(parse_whatsapp_recent())
    prune_whatsapp_artifacts(whatsapp_entries)
    for entry in whatsapp_entries:
        process_whatsapp_entry(state, entry, summary)
    process_whatsapp_threads(state, whatsapp_entries, summary)

    state['last_run'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    public_summary = {k: v for k, v in summary.items() if not k.startswith('_')}
    state['last_summary'] = public_summary
    save_state(state)
    print(json.dumps(public_summary))


if __name__ == '__main__':
    main()

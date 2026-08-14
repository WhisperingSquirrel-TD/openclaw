#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

FINANCE_CODE_ROOT = Path('/home/tomdean88/pi-services/seer-finance')
if str(FINANCE_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_CODE_ROOT))

from seer_finance.ledger.expense_capture_adapter import capture_candidate
from enrichment_queue import enqueue
from expense_outcomes import build_outcome

ROOT = Path('/home/tomdean88')
WORKSPACE = ROOT / '.openclaw' / 'workspace'
CANONICAL_RUNTIME_NAME = 'inbound-watch-router'
CANONICAL_STATE_DIR = ROOT / '.openclaw' / 'runtime' / CANONICAL_RUNTIME_NAME
STATE_FILE = CANONICAL_STATE_DIR / 'state.json'
LOG_FILE = CANONICAL_STATE_DIR / 'watcher.log'
EXPENSE_FILE = WORKSPACE / 'seer-expenses.md'
MONITORED_FILE = WORKSPACE / 'memory' / 'monitored-items-state.json'
MIRROR_EVENTS_FILE = WORKSPACE / 'memory' / 'mirror-events.json'
ENRICHMENT_QUEUE_FILE = ROOT / '.openclaw' / 'runtime' / 'inbound-watch-router' / 'expense-enrichment-queue.json'
MAX_STATE_FILE_BYTES = 8 * 1024 * 1024
MAX_LIFECYCLE_HISTORY = 6
MAX_SCANNED_NON_CANDIDATES = 1_000
MS_READER = ROOT / 'openclaw' / 'pi-services' / 'trusted-email-reader' / 'read_email.py'
GMAIL_READER = ROOT / 'openclaw' / 'pi-services' / 'trusted-email-reader' / 'read_gmail.py'
WHATSAPP_RECENT = WORKSPACE / 'WHATSAPP_RECENT.md'
CONTACTS_FILE = WORKSPACE / 'contacts.md'

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
    'logged': 'processed',
    'duplicate': 'closed',
    'pending': 'blocked',
    'not_needed': 'not_needed',
    'material_non_expense': 'classified',
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
    explicit_outbound: bool = False

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


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r'\D', '', value)
    if not digits:
        return None
    if digits.startswith('44'):
        return '+' + digits
    if digits.startswith('0'):
        return '+44' + digits[1:]
    if value.strip().startswith('+'):
        return '+' + digits
    return '+' + digits


def load_whatsapp_contact_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not CONTACTS_FILE.exists():
        return mapping
    for line in CONTACTS_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line.startswith('- **') or 'Mobile:' not in line:
            continue
        m = re.match(r'- \*\*(.+?)\*\*.*?Mobile:\s*([^|]+)', line)
        if not m:
            continue
        name = m.group(1).strip()
        number = normalize_phone(m.group(2).strip())
        if number:
            mapping[number] = name
    return mapping


WHATSAPP_CONTACT_MAP = load_whatsapp_contact_map()


def canonical_contact_label(label: str | None) -> str | None:
    if not label:
        return None
    label = label.strip()
    num = normalize_phone(label)
    if num and num in WHATSAPP_CONTACT_MAP:
        return WHATSAPP_CONTACT_MAP[num]
    return label


def runtime_dirs() -> list[Path]:
    return [CANONICAL_STATE_DIR]


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
    """Atomically write shared state without a fixed-temp-file race between workers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp', delete=False
    ) as handle:
        json.dump(payload, handle, indent=2)
        handle.flush()
        handle_name = handle.name
    Path(handle_name).replace(path)


def default_state() -> dict[str, Any]:
    return {
        'runtime_name': CANONICAL_RUNTIME_NAME,
        'scanned_non_candidates': [],
        'item_states': {},
        'last_run': None,
        'last_summary': {},
    }


def normalise_state(raw: Any) -> dict[str, Any]:
    """Keep only the watcher schema; never carry legacy router ledgers forward."""
    state = default_state()
    if not isinstance(raw, dict):
        return state
    scanned = raw.get('scanned_non_candidates', [])
    item_states = raw.get('item_states', {})
    state['scanned_non_candidates'] = scanned if isinstance(scanned, list) else []
    state['item_states'] = item_states if isinstance(item_states, dict) else {}
    state['last_run'] = raw.get('last_run')
    state['last_summary'] = raw.get('last_summary') if isinstance(raw.get('last_summary'), dict) else {}
    return state


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return default_state()
    size = STATE_FILE.stat().st_size
    if size > MAX_STATE_FILE_BYTES:
        log(f'Skipping oversized state ({size} bytes): {STATE_FILE}')
        return default_state()
    state = load_json(STATE_FILE, default_state())
    return normalise_state(state) if isinstance(state, dict) else default_state()


def prune_runtime_state(state: dict[str, Any], live_keys: set[str]) -> None:
    """Bound watcher-only state to entries still visible in the rolling feeds.

    Durable outcome proof remains in the canonical expense ledger and monitored
    item ledger; this runtime cache only needs current mirror keys and a short
    diagnostic history.
    """
    item_states = state.setdefault('item_states', {})
    state['item_states'] = {
        key: {
            **value,
            'history': list(value.get('history', []))[-MAX_LIFECYCLE_HISTORY:],
        }
        for key, value in item_states.items()
        if key in live_keys and isinstance(value, dict)
    }
    scanned = [key for key in state.get('scanned_non_candidates', []) if key in live_keys]
    state['scanned_non_candidates'] = sorted(set(scanned))[-MAX_SCANNED_NON_CANDIDATES:]


def save_state(state: dict[str, Any]) -> None:
    state['runtime_name'] = CANONICAL_RUNTIME_NAME
    state.pop('legacy_runtime_name', None)
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


def normalise_mirror_timestamp(raw: object, *, now: datetime | None = None) -> tuple[str, str | None, str]:
    """Return a safe operational timestamp while retaining malformed source time.

    Mirror timestamps are evidence, not trusted control data. A parse failure or
    time more than five minutes in the future is recorded as raw evidence and
    replaced by current observation time so it cannot poison queue ordering.
    """
    current = now or datetime.now(timezone.utc)
    current = current.astimezone(timezone.utc)
    fallback = current.isoformat().replace('+00:00', 'Z')
    raw_text = str(raw or '').strip()
    if not raw_text:
        return fallback, None, 'missing'
    try:
        parsed = datetime.fromisoformat(raw_text.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
    except ValueError:
        return fallback, raw_text, 'invalid'
    if parsed > current + timedelta(minutes=5):
        return fallback, raw_text, 'invalid_future'
    return parsed.isoformat().replace('+00:00', 'Z'), raw_text, 'valid'


def has_transactional_expense_evidence(surface: str, subject: str, reasons: object) -> bool:
    """Reject bare expense-system prose while preserving plausible expense evidence."""
    if surface != 'telegram_inbound':
        return True
    text = f"{subject}\n{' '.join(str(item) for item in (reasons or []))}".lower()
    return bool(re.search(
        r'[$£€]\s*\d|\b(receipt|invoice|order|charged|charge|payment|paid|purchase|purchased|'
        r'renewal|renewed|subscription|refund|reimbursement|debit|credit card|card ending|bank statement)\b',
        text,
    ))


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
    """Extract only stable, identifier-shaped receipt/invoice references.

    Never accept prose such as ``Your`` after the word "invoice": doing so
    turns common words into dedupe keys and can silently close a new cost.
    """
    receipt = None
    invoice = None
    m = re.search(r'#([0-9]{4}-[0-9]{4}-[0-9]{4})', subject)
    if m:
        receipt = m.group(1)
    if not receipt:
        m = re.search(r'Receipt(?: number)?\s*#?\s*([0-9]{4}-[0-9]{4}-[0-9]{4})', text, re.I)
        if m:
            receipt = m.group(1)

    # Invoice IDs must contain a digit and be at least six characters. This
    # accepts Microsoft references such as G175174660 and real invoice IDs,
    # while rejecting prose in phrases like "invoice Your statement".
    invoice_patterns = [
        r'Your Microsoft invoice\s+([A-Z][A-Z0-9-]*[0-9][A-Z0-9-]*)\b',
        r'Invoice(?: number| no\.?)?\s*[:#]?\s*([A-Z][A-Z0-9-]*[0-9][A-Z0-9-]*)\b',
        r'OpenAI API Invoice\s*([A-Z][A-Z0-9-]*[0-9][A-Z0-9-]*)\b',
    ]
    for pattern in invoice_patterns:
        m = re.search(pattern, f'{subject}\n{text}', re.I)
        if m and len(m.group(1)) >= 6:
            invoice = m.group(1)
            break
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
    """Legacy compatibility stub: the Markdown ledger is a read-only archive.

    A live candidate must use SQLite capture or its durable replay fallback;
    a Markdown write is never a valid capture outcome.
    """
    log('legacy seer-expenses.md write suppressed; SQLite capture is mandatory')
    return False


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
    now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    payload = {
        'id': mail_key(entry),
        'surface': f'{entry.account}_{entry.section}',
        'entity': vendor,
        'thread_key': refs.get('invoice') or refs.get('receipt') or entry.subject[:120],
        'source_timestamp': entry.date_str,
        'seen_at': now_iso,
        'management_relevance': 'not_needed' if closure_state == 'not_needed' else 'needs_management',
        'flags': flags,
        'mode': 'watch',
        'closure_state': closure_state,
        'blocker': blocker,
        'evidence_refs': evidence_refs,
        'resolved_at': now_iso if closure_state in ('processed', 'closed', 'not_needed') else None,
        'processed_at': now_iso if closure_state == 'processed' else None,
        'closed_at': now_iso if closure_state == 'closed' else None,
    }
    return payload


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
        contact = contact.strip()
        text = text.strip()
        explicit_outbound = False
        direct_thread_contact = None
        if not group and '->' in contact:
            sender, recipient = [part.strip() for part in contact.split('->', 1)]
            if sender.lower() in {'tom', 'me', 'tom dean'} and recipient:
                explicit_outbound = True
                direct_thread_contact = canonical_contact_label(recipient) or recipient
                contact = 'Me'
        entries.append(WhatsAppEntry(timestamp=ts, group=group, contact=contact, text=text, raw_line=line, direct_thread_contact=direct_thread_contact, explicit_outbound=explicit_outbound))
    return entries


def infer_direct_whatsapp_threads(entries: list[WhatsAppEntry]) -> list[WhatsAppEntry]:
    direct_indices = [idx for idx, entry in enumerate(entries) if entry.is_direct]
    for pos, idx in enumerate(direct_indices):
        entry = entries[idx]
        if not entry.is_me:
            entry.direct_thread_contact = canonical_contact_label(entry.contact) or entry.contact
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

        chosen = entry.direct_thread_contact
        chosen_is_number = bool(chosen and normalize_phone(chosen))
        if prev_contact and next_contact and prev_contact.lower() == next_contact.lower():
            if prev_dt and next_dt and (entry.timestamp_dt - prev_dt) <= WHATSAPP_DIRECT_THREAD_LINK_WINDOW and (next_dt - entry.timestamp_dt) <= WHATSAPP_DIRECT_THREAD_LINK_WINDOW:
                chosen = prev_contact
        if (not chosen or chosen_is_number) and prev_contact and prev_dt and (entry.timestamp_dt - prev_dt) <= WHATSAPP_DIRECT_THREAD_LINK_WINDOW:
            chosen = prev_contact
        if (not chosen or chosen_is_number) and next_contact and next_dt and (next_dt - entry.timestamp_dt) <= WHATSAPP_DIRECT_THREAD_LINK_WINDOW:
            chosen = next_contact
        entry.direct_thread_contact = canonical_contact_label(chosen) or chosen
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
    now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    return {
        'id': entry.key,
        'surface': 'whatsapp_recent',
        'entity': entry.direct_thread_contact or entry.contact,
        'thread_key': entry.thread_key,
        'source_timestamp': entry.timestamp,
        'seen_at': now_iso,
        'management_relevance': 'not_needed' if closure_state == 'not_needed' else 'needs_management',
        'flags': flags or ['EXPENSE'],
        'mode': 'watch',
        'closure_state': closure_state,
        'blocker': blocker,
        'evidence_refs': evidence_refs or ['seer-expenses.md'],
        'resolved_at': now_iso if closure_state in ('processed', 'closed', 'not_needed') else None,
        'processed_at': now_iso if closure_state == 'processed' else None,
        'closed_at': now_iso if closure_state == 'closed' else None,
    }


def capture_sqlite_candidate(*, source_surface: str, source_ref: str, source_timestamp: str | None = None,
                             supplier: str | None = None, evidence_ref: str | None = None):
    """Capture once and return the real SQLite-or-replay outcome to every caller.

    Callers must never label a candidate as captured merely because this boundary
    was invoked: `captured` requires an expense ID; `replayed` is a blocked,
    durable fallback which the autonomous runtime must retry without TOTP.
    """
    facts = {
        'source_timestamp': source_timestamp,
        'supplier': supplier,
        'evidence_ref': evidence_ref,
        'evidence_state': 'retained' if evidence_ref else 'source_visible',
    }
    result = capture_candidate(source_surface=source_surface, source_ref=source_ref, facts=facts)
    log(f'sqlite capture {result.outcome} source_ref={source_ref} expense_id={result.expense_id or ""} blocker={result.blocker or ""}')
    return result


def mark_state(state: dict[str, Any], key: str, route: str, status: str, detail: str | None = None) -> None:
    state.setdefault('item_states', {})[key] = {
        'route': route,
        'status': status,
        'detail': detail,
        'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
    }


def advance_item_lifecycle(state: dict[str, Any], key: str, route: str, stage: str, detail: str | None = None) -> None:
    current = state.setdefault('item_states', {}).get(key, {})
    history = list(current.get('history', []))
    now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    history.append({'stage': stage, 'detail': detail, 'at': now_iso})
    history = history[-MAX_LIFECYCLE_HISTORY:]
    state['item_states'][key] = {
        'route': route,
        'status': stage,
        'detail': detail,
        'updated_at': now_iso,
        'history': history,
    }


def lifecycle_payload(base: dict[str, Any], stage: str, blocker: str | None = None) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    payload = dict(base)
    payload['closure_state'] = stage
    payload['blocker'] = blocker
    payload['management_relevance'] = 'not_needed' if stage == 'not_needed' else 'needs_management'
    payload['resolved_at'] = now_iso if stage in ('processed', 'closed', 'not_needed') else None
    payload['processed_at'] = now_iso if stage == 'processed' else payload.get('processed_at')
    payload['closed_at'] = now_iso if stage == 'closed' else payload.get('closed_at')
    if stage == 'closed' and not payload.get('processed_at'):
        payload['processed_at'] = payload.get('resolved_at') or now_iso
    return payload


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

        legacy_blocked_expense = closure_state in {'blocked'} and ('expense signal needs business relevance' in blocker)
        stale_classified_nonlive = closure_state in {'classified'} and thread_key and thread_key not in live_direct_thread_keys and stale_source
        stale_classified_live_nonactionable = closure_state in {'classified'} and item_id in live_keys and item_id not in live_actionable_keys and stale_source
        noisy_priority_item = closure_state in {'classified'} and entity in WHATSAPP_PRIORITY_CONTACTS and item_id not in live_actionable_keys
        no_longer_actionable_live_item = item_id in live_keys and item_id not in live_actionable_keys and closure_state in {'classified', 'blocked', 'closed'}

        stale_surfaced_nonlive = stale_classified_nonlive
        stale_surfaced_live_nonactionable = stale_classified_live_nonactionable

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
        # seer-expenses.md is retained read-only evidence after SQLite cutover.
        # Never fail the live watcher by attempting legacy archival cleanup.
        log('legacy seer-expenses.md cleanup suppressed; archive is read-only')


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
                            'routed',
                            'Latest actionable inbound in direct thread has no later visible Me: reply yet',
                            flags=sorted(set(flags + ['OUTBOUND_CONTEXT'])),
                            evidence_refs=['WHATSAPP_RECENT.md', 'memory/monitored-items-state.json'],
                        ),
                    )
                    advance_item_lifecycle(state, latest.key, 'whatsapp', 'routed', 'Direct thread still waiting on Tom reply')
            continue

        if latest and latest.is_me and outbound_follow_up_signal(latest):
            has_later_inbound = any((not entry.is_me and entry.timestamp_dt > latest.timestamp_dt) for entry in thread_entries)
            if not has_later_inbound and latest.timestamp_dt >= now - WHATSAPP_HANGING_OUTBOUND_WINDOW:
                summary['material_non_expense'] += 1
                upsert_monitored(
                    latest.key,
                    whatsapp_monitored_payload(
                        latest,
                        'routed',
                        'Tom sent the latest direct follow-up/chase and there is no later visible reply yet',
                        flags=['FOLLOW_UP', 'OUTBOUND_CONTEXT'],
                        evidence_refs=['WHATSAPP_RECENT.md', 'memory/monitored-items-state.json'],
                    ),
                )
                advance_item_lifecycle(state, latest.key, 'whatsapp', 'routed', 'Direct thread may need chase tracking')


def process_email_entry(state: dict[str, Any], entry: MailEntry, summary: dict[str, int]) -> None:
    key = mail_key(entry)
    scanned = set(state.get('scanned_non_candidates', []))
    current = state.get('item_states', {}).get(key, {})
    flags = classify_email_flags(entry)
    refs = extract_refs(entry.subject, entry.body_preview)
    base_payload = email_monitored_payload(entry, 'trigger_received', None, refs, flags=flags)

    summary['reviewed'] += 1
    advance_item_lifecycle(state, key, 'email', 'trigger_received', ','.join(flags))
    upsert_monitored(key, lifecycle_payload(base_payload, 'trigger_received'))

    if 'IGNORE' in flags and not materially_important_email(entry, flags):
        remove_monitored(key)
        summary['not_needed'] += 1
        if key not in scanned:
            scanned.add(key)
            state['scanned_non_candidates'] = sorted(scanned)
        advance_item_lifecycle(state, key, 'email', 'not_needed', 'No routed signal detected in mirror')
        return

    advance_item_lifecycle(state, key, 'email', 'classified', ','.join(flags))
    upsert_monitored(key, lifecycle_payload(base_payload, 'classified'))

    if 'EXPENSE' not in flags:
        if materially_important_email(entry, flags):
            material_key = f"{entry.account}:{entry.section}:{tuple(flags)}:{entry.subject.strip().lower()[:160]}"
            seen_material = set(summary.setdefault('_seen_material_keys', []))
            if material_key not in seen_material:
                summary['material_non_expense'] += 1
                seen_material.add(material_key)
                summary['_seen_material_keys'] = sorted(seen_material)
            advance_item_lifecycle(state, key, 'email', 'routed', 'Managed non-expense item routed for visibility/reconciliation')
            upsert_monitored(key, lifecycle_payload(base_payload, 'routed', None))
        else:
            remove_monitored(key)
            summary['not_needed'] += 1
            if key not in scanned:
                scanned.add(key)
                state['scanned_non_candidates'] = sorted(scanned)
            advance_item_lifecycle(state, key, 'email', 'not_needed', 'No routed signal detected in mirror')
        return

    summary['expense_candidates'] += 1
    capture = capture_sqlite_candidate(source_surface=f'email:{entry.account}:{entry.section}', source_ref=key,
                                       source_timestamp=entry.date_str, supplier=entry.party, evidence_ref=f'{entry.mailbox_path}:{entry.message_id}')
    if capture.outcome == 'captured':
        routed_detail = f'Captured in SQLite expense_id={capture.expense_id}'
        blocker = 'Captured in SQLite; explicit review/enrichment is required before finance posting'
    else:
        routed_detail = 'SQLite capture failed; durable replay preserved'
        blocker = f'Durable SQLite replay pending autonomous retry: {capture.blocker}'
    advance_item_lifecycle(state, key, 'email', 'routed', routed_detail)
    upsert_monitored(key, lifecycle_payload(base_payload, 'routed'))
    advance_item_lifecycle(state, key, 'email', 'blocked', blocker)
    upsert_monitored(key, lifecycle_payload(base_payload, 'blocked', blocker))
    summary['pending'] += 1


def process_whatsapp_entry(state: dict[str, Any], entry: WhatsAppEntry, summary: dict[str, int]) -> None:
    key = entry.key
    scanned = set(state.get('scanned_non_candidates', []))
    flags = classify_whatsapp_flags(entry)
    base_payload = whatsapp_monitored_payload(entry, 'trigger_received', None, flags=flags)

    advance_item_lifecycle(state, key, 'whatsapp', 'trigger_received', ','.join(flags))
    upsert_monitored(key, lifecycle_payload(base_payload, 'trigger_received'))

    if 'IGNORE' in flags and not materially_important_whatsapp(entry, flags):
        remove_monitored(key)
        if key not in scanned:
            scanned.add(key)
            state['scanned_non_candidates'] = sorted(scanned)
        summary['not_needed'] += 1
        advance_item_lifecycle(state, key, 'whatsapp', 'not_needed', 'No strong routed signal detected in WhatsApp recent feed')
        return

    advance_item_lifecycle(state, key, 'whatsapp', 'classified', ','.join(flags))
    upsert_monitored(key, lifecycle_payload(base_payload, 'classified'))

    if 'EXPENSE' not in flags:
        if entry.is_direct and (not entry.group) and (not entry.is_me or entry.direct_thread_contact):
            remove_monitored(key)
            if key not in scanned:
                scanned.add(key)
                state['scanned_non_candidates'] = sorted(scanned)
            summary['not_needed'] += 1
            advance_item_lifecycle(state, key, 'whatsapp', 'not_needed', 'Direct-thread non-expense signals are reconciled at thread level with Me: context')
            return
        if materially_important_whatsapp(entry, flags):
            summary['material_non_expense'] += 1
            advance_item_lifecycle(state, key, 'whatsapp', 'routed', 'Managed non-expense item routed for visibility/reconciliation')
            upsert_monitored(key, lifecycle_payload(base_payload, 'routed'))
        else:
            if key not in scanned:
                scanned.add(key)
                state['scanned_non_candidates'] = sorted(scanned)
            summary['not_needed'] += 1
            advance_item_lifecycle(state, key, 'whatsapp', 'not_needed', 'No strong routed signal detected in WhatsApp recent feed')
        return

    summary['expense_candidates'] += 1
    capture = capture_sqlite_candidate(source_surface='whatsapp_recent', source_ref=key,
                                       source_timestamp=entry.timestamp, supplier=entry.contact, evidence_ref='WHATSAPP_RECENT.md')
    if capture.outcome == 'captured':
        routed_detail = f'Captured in SQLite expense_id={capture.expense_id}'
        blocker = 'Captured in SQLite; WhatsApp expense signal needs explicit business/payment/evidence review before finance posting'
    else:
        routed_detail = 'SQLite capture failed; durable replay preserved'
        blocker = f'Durable SQLite replay pending autonomous retry: {capture.blocker}'
    advance_item_lifecycle(state, key, 'whatsapp', 'routed', routed_detail)
    upsert_monitored(key, lifecycle_payload(base_payload, 'routed'))
    advance_item_lifecycle(state, key, 'whatsapp', 'blocked', blocker)
    upsert_monitored(key, lifecycle_payload(base_payload, 'blocked', blocker))
    summary['pending'] += 1


def mirror_expense_keys() -> set[str]:
    raw = load_json(MIRROR_EVENTS_FILE, {})
    events = raw.get('items', []) if isinstance(raw, dict) else []
    if not isinstance(events, list):
        return set()
    return {
        f"mirror-expense:{str(event.get('stable_item_key') or event.get('source_id'))}"
        for event in events
        if isinstance(event, dict)
        and 'EXPENSE' in set(event.get('routing_flags') or [])
        and (event.get('stable_item_key') or event.get('source_id'))
    }


def process_mirror_expense_events(state: dict[str, Any], summary: dict[str, int]) -> None:
    """Preserve new expense candidates emitted by the central all-surface router.

    This is deliberately a blocker-first adapter.  Trusted inbox events still
    use the existing full-body reader path; external, sent and Teams events are
    never silently ignored merely because that reader is unavailable.  A later
    enrichment/ledger worker must advance the explicit blocker rather than
    reclassifying it from a loose text match.
    """
    raw = load_json(MIRROR_EVENTS_FILE, {})
    events = raw.get('items', []) if isinstance(raw, dict) else []
    if not isinstance(events, list):
        return
    for event in events:
        if not isinstance(event, dict) or 'EXPENSE' not in set(event.get('routing_flags') or []):
            continue
        stable = str(event.get('stable_item_key') or event.get('source_id') or '')
        surface = str(event.get('surface') or '')
        if not stable or not surface:
            continue
        key = f'mirror-expense:{stable}'
        existing = state.setdefault('item_states', {}).get(key, {})
        if existing.get('status') in {'blocked', 'closed', 'not_needed'}:
            continue
        subject = str(event.get('subject_or_location') or 'Expense signal')
        source_ref = str(event.get('raw_evidence_ref') or event.get('proof_source') or 'mirror-events.json')
        source_id = str(event.get('source_id') or stable)
        reasons = event.get('reasons') or []
        safe_source_timestamp, raw_source_timestamp, timestamp_status = normalise_mirror_timestamp(
            event.get('source_timestamp')
        )
        if not has_transactional_expense_evidence(surface, subject, reasons):
            reason = 'central EXPENSE flag had no transactional evidence; retained as not-needed mirror evidence'
            outcome = build_outcome(
                source_id=source_id,
                source_surface=surface,
                expense_outcome='not_needed',
                canonical_ref=None,
                ledger_state='not_required',
                evidence_state='not_required',
                candidate_reason=reason,
                observed_at=safe_source_timestamp,
            )
            upsert_monitored(key, {
                'id': key,
                'surface': surface,
                'entity': 'Mirror intake',
                'thread_key': str(event.get('thread_key') or source_id),
                'source_timestamp': safe_source_timestamp,
                'raw_source_timestamp': raw_source_timestamp,
                'source_timestamp_status': timestamp_status,
                'seen_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'management_relevance': 'not_needed',
                'flags': ['EXPENSE'],
                'mode': 'watch',
                'closure_state': 'not_needed',
                'expense_outcome': outcome.expense_outcome,
                'canonical_ref': None,
                'ledger_state': outcome.ledger_state,
                'evidence_state': outcome.evidence_state,
                'blocker': None,
                'candidate_reason': reason,
                'evidence_refs': [source_ref],
                'resolved_at': safe_source_timestamp,
                'processed_at': safe_source_timestamp,
                'closed_at': safe_source_timestamp,
            })
            advance_item_lifecycle(state, key, 'mirror_expense', 'not_needed', reason)
            summary['mirror_not_needed'] = summary.get('mirror_not_needed', 0) + 1
            continue
        capture = capture_sqlite_candidate(source_surface=surface, source_ref=source_id, source_timestamp=safe_source_timestamp,
                                           supplier=subject, evidence_ref=source_ref)
        if capture.outcome == 'captured':
            canonical_ref = f'sqlite:{capture.expense_id}'
            blocker = 'SQLite capture requires expense enrichment before ledger/evidence completion'
        else:
            canonical_ref = f'sqlite-replay:{source_id}'
            blocker = f'Durable SQLite replay pending autonomous retry: {capture.blocker}'
        outcome = build_outcome(
            source_id=source_id,
            source_surface=surface,
            expense_outcome='blocked',
            canonical_ref=canonical_ref,
            ledger_state='pending',
            evidence_state='blocked',
            blocker=blocker,
            candidate_reason='; '.join(str(x) for x in reasons[:3]) or 'central router expense classification',
        )
        now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        payload = {
            'id': key,
            'surface': surface,
            'entity': 'Mirror intake',
            'thread_key': str(event.get('thread_key') or source_id),
            'source_timestamp': safe_source_timestamp,
            'raw_source_timestamp': raw_source_timestamp,
            'source_timestamp_status': timestamp_status,
            'seen_at': now_iso,
            'management_relevance': 'needs_management',
            'flags': ['EXPENSE'],
            'mode': 'watch',
            'closure_state': 'blocked',
            'expense_outcome': outcome.expense_outcome,
            'canonical_ref': outcome.canonical_ref,
            'ledger_state': outcome.ledger_state,
            'evidence_state': outcome.evidence_state,
            'blocker': outcome.blocker,
            'evidence_refs': [source_ref, canonical_ref],
            'resolved_at': None,
            'processed_at': None,
            'closed_at': None,
        }
        upsert_monitored(key, payload)
        advance_item_lifecycle(state, key, 'mirror_expense', 'blocked', blocker)
        summary['mirror_blocked'] = summary.get('mirror_blocked', 0) + 1


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

    email_entries = [
        entry
        for account, path in EMAIL_SOURCES
        for entry in parse_mail_sections(account, path)
    ]
    whatsapp_entries = infer_direct_whatsapp_threads(parse_whatsapp_recent())
    live_keys = {mail_key(entry) for entry in email_entries} | {entry.key for entry in whatsapp_entries} | mirror_expense_keys()
    prune_runtime_state(state, live_keys)

    for entry in email_entries:
        process_email_entry(state, entry, summary)

    prune_whatsapp_artifacts(whatsapp_entries)
    for entry in whatsapp_entries:
        process_whatsapp_entry(state, entry, summary)
    process_whatsapp_threads(state, whatsapp_entries, summary)
    process_mirror_expense_events(state, summary)

    state['last_run'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    public_summary = {k: v for k, v in summary.items() if not k.startswith('_')}
    state['last_summary'] = public_summary
    save_state(state)
    print(json.dumps(public_summary))


if __name__ == '__main__':
    main()

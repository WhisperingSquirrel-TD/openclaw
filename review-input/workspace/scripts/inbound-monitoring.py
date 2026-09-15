#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mirror_router import MirrorEvent, classify_mirror_event, classify_website_intake_item, event_from_dict, event_to_dict, load_crm_entity_candidates, load_live_crm_entity_types, normalize_website_intake_item
from intake_ledger import (
    record_event as record_intake_event,
    record_receipt as record_intake_receipt,
    update_surface_health as update_intake_surface_health,
)

WORKSPACE = Path("/home/tomdean88/.openclaw/workspace")
CRM_PATH = WORKSPACE / "stackstone/crm.md"
PARTNERSHIPS_PATH = WORKSPACE / "stackstone/partnerships.md"
STATE_PATH = WORKSPACE / "memory/monitored-items-state.json"
SURFACE_STATE_PATH = WORKSPACE / "memory/monitoring-surface-state.json"
CRM_RECON_PATH = WORKSPACE / "memory/crm-sharepoint-reconciliation.md"
BLOCKED_REPORT_PATH = WORKSPACE / "memory/blocked-monitored-items.md"
OP_LOG_RECON_PATH = WORKSPACE / "memory/operational-activity-log-reconciliation.md"
PROOF_LAYER_RECON_PATH = WORKSPACE / "memory/proof-layer-reconciliation.md"
OUTBOUND_COMPLETION_PATH = WORKSPACE / "memory/outbound-completion-audit.md"
BOUNCE_UNSUB_PATH = WORKSPACE / "memory/bounce-unsub-audit.md"
READABLE_TRUTH_PATH = WORKSPACE / "memory/readable-truth-audit.md"
SURFACE_REPORT_PATH = WORKSPACE / "memory/website-activity-continuity.md"
GMAIL_SURFACE_REPORT_PATH = WORKSPACE / "memory/gmail-continuity.md"
MICROSOFT_SURFACE_REPORT_PATH = WORKSPACE / "memory/microsoft-inbox-continuity.md"
WHATSAPP_SURFACE_REPORT_PATH = WORKSPACE / "memory/whatsapp-continuity.md"
ASSISTANT_INBOX_SURFACE_REPORT_PATH = WORKSPACE / "memory/assistant-inbox-continuity.md"
ASSISTANT_EXTERNAL_SURFACE_REPORT_PATH = WORKSPACE / "memory/assistant-external-continuity.md"
GMAIL_EXTERNAL_SURFACE_REPORT_PATH = WORKSPACE / "memory/gmail-external-continuity.md"
MICROSOFT_EXTERNAL_SURFACE_REPORT_PATH = WORKSPACE / "memory/microsoft-external-continuity.md"
SURFACE_AUDIT_PATH = WORKSPACE / "memory/monitoring-surface-audit.md"
SHAREPOINT_FILE_WATCH_STATE_PATH = WORKSPACE / "memory/sharepoint-file-watch-state.json"
SHAREPOINT_ENTITY_WATCH_STATE_PATH = WORKSPACE / "memory/sharepoint-entity-watch-state.json"
SHAREPOINT_BLOCKED_STATE_PATH = WORKSPACE / "memory/sharepoint-origin-blocked-state.json"
SHAREPOINT_NORMALIZATION_HISTORY_PATH = WORKSPACE / "memory/sharepoint-normalization-history.json"
SHAREPOINT_ORIGIN_RECON_PATH = WORKSPACE / "memory/sharepoint-origin-reconciliation.md"
SHAREPOINT_MANIFEST_PATH = WORKSPACE / "sharepoint-cache/.manifest.json"
SHAREPOINT_QUEUE_PATH = Path.home() / ".openclaw/sharepoint-queue.json"
OP_LOG_PATH = WORKSPACE / "reference/OPERATIONAL_ACTIVITY_LOG.md"
SHAREPOINT_RESULT_PATH = WORKSPACE / "SHAREPOINT_RESULT.md"
INVOICE_TRACKER_PATH = WORKSPACE / "INVOICE_TRACKER.md"
# SQLite is the sole expense-status authority. `seer-expenses.md` is a
# read-only historic evidence archive and must never drive monitoring closure.
FINANCE_DB_PATH = Path("/home/tomdean88/pi-services/seer-finance/data/expense-ledger.sqlite3")
SYSTEM_HEALTH_PATH = WORKSPACE / "SYSTEM_HEALTH.md"
WHATSAPP_RECENT_PATH = WORKSPACE / "WHATSAPP_RECENT.md"
WHATSAPP_WINDOW_PATH = WORKSPACE / "memory/whatsapp-recent-window.json"
TEAMS_RECENT_PATH = WORKSPACE / "TEAMS_RECENT.md"
TEAMS_RECENT_JSON_PATH = WORKSPACE / "memory/teams-recent.json"
TEAMS_ROUTING_REPORT_PATH = WORKSPACE / "memory/teams-routing.md"
MIRROR_EVENTS_JSON_PATH = WORKSPACE / "memory/mirror-events.json"
MIRROR_ROUTING_REPORT_PATH = WORKSPACE / "memory/mirror-routing.md"
MIRROR_ROUTER_STATE_PATH = WORKSPACE / "memory/mirror-router-state.json"
INTAKE_ACTIONS_PATH = WORKSPACE / "memory/intake-actions.json"
MAX_SEEN_EVENTS_PER_SURFACE = 500
STACKSTONE_LEADS_PATH = WORKSPACE / "STACKSTONE_LEADS.md"
GMAIL_INBOX_PATH = WORKSPACE / "GMAIL_INBOX.md"
MICROSOFT_INBOX_PATH = WORKSPACE / "MICROSOFT_INBOX.md"
ASSISTANT_INBOX_PATH = WORKSPACE / "ASSISTANT_INBOX.md"
ASSISTANT_EXTERNAL_PATH = WORKSPACE / "ASSISTANT_EXTERNAL.md"
GMAIL_EXTERNAL_PATH = WORKSPACE / "GMAIL_EXTERNAL.md"
MICROSOFT_EXTERNAL_PATH = WORKSPACE / "MICROSOFT_EXTERNAL.md"
PENDING_BOUNCES_PATH = Path('/home/tomdean88/prospector/pending_bounces.txt')
PENDING_UNSUBS_PATH = Path('/home/tomdean88/prospector/pending_unsubs.txt')

MAILBOX_PATHS = [
    WORKSPACE / "MICROSOFT_INBOX.md",
    WORKSPACE / "ASSISTANT_INBOX.md",
    WORKSPACE / "GMAIL_INBOX.md",
]

SURFACE_SPECS = {
    "stackstone_leads": {
        "source_path": STACKSTONE_LEADS_PATH,
        "title": "Website Activity Continuity Report",
        "threshold_hours": 4,
        "kind": "website",
        "report_path": SURFACE_REPORT_PATH,
    },
    "microsoft_inbox": {
        "source_path": MICROSOFT_INBOX_PATH,
        "title": "Microsoft Inbox Continuity Report",
        "threshold_hours": 2,
        "kind": "inbound",
        "report_path": MICROSOFT_SURFACE_REPORT_PATH,
    },
    "assistant_inbox": {
        "source_path": ASSISTANT_INBOX_PATH,
        "title": "Assistant Inbox Continuity Report",
        "threshold_hours": 2,
        "kind": "inbound",
        "report_path": ASSISTANT_INBOX_SURFACE_REPORT_PATH,
    },
    "gmail_inbox": {
        "source_path": GMAIL_INBOX_PATH,
        "title": "Gmail Continuity Report",
        "threshold_hours": 2,
        "kind": "inbound",
        "report_path": GMAIL_SURFACE_REPORT_PATH,
    },
    "microsoft_external": {
        "source_path": MICROSOFT_EXTERNAL_PATH,
        "title": "Microsoft External Continuity Report",
        "threshold_hours": 2,
        "kind": "inbound",
        "report_path": MICROSOFT_EXTERNAL_SURFACE_REPORT_PATH,
    },
    "assistant_external": {
        "source_path": ASSISTANT_EXTERNAL_PATH,
        "title": "Assistant External Continuity Report",
        "threshold_hours": 2,
        "kind": "inbound",
        "report_path": ASSISTANT_EXTERNAL_SURFACE_REPORT_PATH,
    },
    "gmail_external": {
        "source_path": GMAIL_EXTERNAL_PATH,
        "title": "Gmail External Continuity Report",
        "threshold_hours": 2,
        "kind": "inbound",
        "report_path": GMAIL_EXTERNAL_SURFACE_REPORT_PATH,
    },
    "whatsapp_recent": {
        "source_path": WHATSAPP_RECENT_PATH,
        "title": "WhatsApp Continuity Report",
        "threshold_hours": 2,
        "kind": "chat",
        "report_path": WHATSAPP_SURFACE_REPORT_PATH,
    },
    "teams_recent": {
        "source_path": TEAMS_RECENT_PATH,
        "title": "Teams Continuity Report",
        "threshold_hours": 2,
        "kind": "chat",
        "report_path": WORKSPACE / "memory/teams-continuity.md",
    },
    "assistant_sent": {
        "source_path": ASSISTANT_INBOX_PATH,
        "title": "Assistant Sent Continuity Report",
        "threshold_hours": 2,
        "kind": "outbound",
        "report_path": WORKSPACE / "memory/assistant-sent-continuity.md",
        "section_heading": "## Sent Items",
    },
    "gmail_sent": {
        "source_path": GMAIL_INBOX_PATH,
        "title": "Gmail Sent Continuity Report",
        "threshold_hours": 2,
        "kind": "outbound",
        "report_path": WORKSPACE / "memory/gmail-sent-continuity.md",
        # Gmail's mirrored outbound section is intentionally named differently
        # from the Microsoft/assistant mirrors. Keep this source-owned mapping
        # here so the generic continuity engine reads the real feed, not a
        # nonexistent "Sent Items" section.
        "section_heading": "## Sent Mail",
    },
    "microsoft_sent": {
        "source_path": MICROSOFT_INBOX_PATH,
        "title": "Microsoft Sent Continuity Report",
        "threshold_hours": 2,
        "kind": "outbound",
        "report_path": WORKSPACE / "memory/microsoft-sent-continuity.md",
        "section_heading": "## Sent Items",
    },
}

FIRST_CLASS_INTAKE_SURFACES = (
    "microsoft_inbox",
    "microsoft_external",
    "assistant_inbox",
    "assistant_external",
    "gmail_inbox",
    "gmail_external",
    "whatsapp_recent",
    "teams_recent",
)

OUTBOUND_CONTEXT_SURFACES = (
    "assistant_sent",
    "gmail_sent",
    "microsoft_sent",
)

ALL_MONITORED_SURFACES = FIRST_CLASS_INTAKE_SURFACES + OUTBOUND_CONTEXT_SURFACES


@dataclass
class EntityRow:
    section: str
    company: str
    primary_contact: str
    stage: str
    last_touch: str
    next_step: str
    campaign_eligible: str
    sharepoint_path: str


@dataclass
class EvidenceHit:
    mailbox: str
    timestamp: datetime
    summary: str


@dataclass
class SharePointFileCandidate:
    path: str
    file_class: str
    entity_kind: str | None
    entity_name: str | None
    modified: str | None
    size: int | None
    local_path: str | None
    change_state: str
    reason: str

    @property
    def entity_key(self) -> str | None:
        if not self.entity_kind or not self.entity_name:
            return None
        return f"{self.entity_kind}:{self.entity_name}"


DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
CURRENT_LAST_TOUCH_RE = re.compile(r"\*\*Last touch:\*\*\s*(\d{4}-\d{2}-\d{2})")
SYNC_RE = re.compile(r"synced:\s*([0-9T:\-]+Z)")
LAST_UPDATED_RE = re.compile(r"^Last updated:\s*(.+)$", re.MULTILINE)
WHATSAPP_LINE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]", re.MULTILINE)
TEAMS_LINE_RE = re.compile(r"^- \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC\]", re.MULTILINE)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    ts = ts.strip()
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("Europe/London"))
        return dt.astimezone(timezone.utc)
    except ValueError:
        try:
            dt = parsedate_to_datetime(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("Europe/London"))
            return dt.astimezone(timezone.utc)
        except Exception:
            return None


def parse_ddmmyyyy(value: str) -> datetime | None:
    m = DATE_RE.search(value or "")
    if not m:
        return None
    day, month, year = map(int, m.groups())
    return datetime(year, month, day, tzinfo=timezone.utc)


def extract_table_rows(lines: list[str], header: str) -> list[EntityRow]:
    rows: list[EntityRow] = []
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == header:
            start = idx
            break
    if start is None:
        return rows
    for idx in range(start + 2, len(lines)):
        line = lines[idx].rstrip("\n")
        if not line.strip():
            break
        if not line.startswith("|"):
            break
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 7 or parts[0] == "Company":
            continue
        if all(set(part) <= {"-", ":", " "} for part in parts):
            continue
        # The control pattern intentionally uses `|` inside Next Step. Locate
        # the deterministic SharePoint path from the right instead of assuming
        # a fixed table column; otherwise a valid control row corrupts its own
        # entity-path mapping.
        path_idx = next((i for i, value in enumerate(parts) if value.startswith("/Accounts/") or value.startswith("/Opportunities/")), None)
        if path_idx is None or path_idx < 6:
            continue
        rows.append(
            EntityRow(
                section=header.strip("# "),
                company=parts[0],
                primary_contact=parts[1],
                stage=parts[2],
                last_touch=parts[3],
                next_step=" | ".join(parts[4:path_idx - 1]),
                campaign_eligible=parts[path_idx - 1],
                sharepoint_path=parts[path_idx],
            )
        )
    return rows


def load_entities() -> list[EntityRow]:
    lines = CRM_PATH.read_text().splitlines()
    return extract_table_rows(lines, "## Opportunities") + extract_table_rows(lines, "## Accounts")


def slug_to_cache_path(sharepoint_path: str) -> Path | None:
    raw = sharepoint_path.strip()
    if not raw:
        return None
    if raw.startswith("sites/"):
        raw = "/" + raw
    if not raw.startswith("/"):
        raw = "/" + raw
    cache_path = WORKSPACE / "sharepoint-cache" / raw.lstrip("/")
    return cache_path


def parse_current_file_info(cache_path: Path) -> tuple[datetime | None, datetime | None]:
    if not cache_path.exists():
        return None, None
    text = cache_path.read_text(errors="ignore")
    m1 = CURRENT_LAST_TOUCH_RE.search(text)
    current_touch = parse_iso(m1.group(1) + "T00:00:00+00:00") if m1 else None
    m2 = SYNC_RE.search(text)
    synced_at = parse_iso(m2.group(1)) if m2 else None
    return current_touch, synced_at


def load_last_scan_timestamp() -> datetime | None:
    path = WORKSPACE / "memory/last-seen-emails.md"
    if not path.exists():
        return None
    for line in path.read_text().splitlines()[::-1]:
        if line.startswith("last_scan_timestamp:"):
            return parse_iso(line.split(":", 1)[1].strip())
    return None


def split_message_blocks(text: str) -> Iterable[list[str]]:
    block: list[str] = []
    for line in text.splitlines():
        if line.startswith("---"):
            if block:
                yield block
                block = []
            continue
        block.append(line)
    if block:
        yield block


def parse_block_timestamp(block: list[str]) -> datetime | None:
    for line in block:
        if " | 20" in line and (line.startswith("From:") or line.startswith("To:")):
            try:
                ts = line.rsplit("|", 1)[1].strip()
                return parse_iso(ts)
            except Exception:
                return None
    return None


def block_text(block: list[str]) -> str:
    return "\n".join(block)


def matches_entity(entity: EntityRow, text: str) -> bool:
    text_lower = text.lower()
    company_pattern = re.compile(rf"\b{re.escape(entity.company.lower())}\b")
    if company_pattern.search(text_lower):
        return True
    contacts = [c.strip() for c in re.split(r"/|,", entity.primary_contact) if c.strip()]
    for contact in contacts:
        contact_pattern = re.compile(rf"\b{re.escape(contact.lower())}\b")
        if contact_pattern.search(text_lower):
            return True
        pieces = contact.split()
        if len(pieces) >= 2:
            full_name_pattern = re.compile(rf"\b{re.escape(pieces[0].lower())}\s+{re.escape(pieces[-1].lower())}\b")
            if full_name_pattern.search(text_lower):
                return True
    return False


def find_recent_evidence(entity: EntityRow, since: datetime | None, lookback_days: int = 14) -> list[EvidenceHit]:
    cutoff = since or (now_utc() - timedelta(days=lookback_days))
    hits: list[EvidenceHit] = []
    for path in MAILBOX_PATHS:
        if not path.exists():
            continue
        for block in split_message_blocks(path.read_text(errors="ignore")):
            ts = parse_block_timestamp(block)
            if not ts or ts < cutoff:
                continue
            text = block_text(block)
            if matches_entity(entity, text):
                subj = next((ln.strip("* ") for ln in block if ln.startswith("**") and ln.endswith("**")), "(no subject)")
                hits.append(EvidenceHit(path.name, ts, subj[:180]))
    hits.sort(key=lambda h: h.timestamp, reverse=True)
    return hits


def format_hit(hit: EvidenceHit) -> str:
    return f"- {hit.timestamp.strftime('%Y-%m-%d %H:%M')} UTC — `{hit.mailbox}` — {hit.summary}"


def crm_sharepoint_reconciliation() -> str:
    entities = load_entities()
    last_scan = load_last_scan_timestamp()
    lines: list[str] = []
    lines.append("# CRM / SharePoint Reconciliation")
    lines.append(f"_Generated: {now_utc().strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")
    lines.append("## Scope")
    lines.append("Recent CRM Accounts/Opportunities vs recent mailbox movement and cached SharePoint Current files.")
    lines.append("")
    stale_count = 0
    coverage_incomplete = []
    for entity in entities:
        crm_touch = parse_ddmmyyyy(entity.last_touch)
        cache_path = slug_to_cache_path(entity.sharepoint_path)
        current_touch, synced_at = parse_current_file_info(cache_path) if cache_path else (None, None)
        evidence = find_recent_evidence(entity, last_scan)
        crm_stale = False
        sharepoint_stale = False
        blocker = None
        exact_action = None
        if evidence and crm_touch:
            latest_evidence = max(h.timestamp for h in evidence)
            if latest_evidence.date() > crm_touch.date():
                crm_stale = True
        if crm_touch and current_touch and crm_touch.date() > current_touch.date():
            sharepoint_stale = True
        elif evidence and current_touch:
            latest_evidence = max(h.timestamp for h in evidence)
            if latest_evidence.date() > current_touch.date():
                sharepoint_stale = True
        if cache_path and not cache_path.exists():
            blocker = f"Current file missing from cache for path `{entity.sharepoint_path}`"
            coverage_incomplete.append(entity.company)
        if crm_stale or sharepoint_stale or blocker:
            stale_count += 1
            lines.append(f"## {entity.company}")
            lines.append(f"- Section: {entity.section}")
            lines.append(f"- Stage: {entity.stage}")
            lines.append(f"- CRM Last Touch: {entity.last_touch}")
            lines.append(f"- SharePoint path: `{entity.sharepoint_path}`")
            lines.append(f"- Cached Current touch: {current_touch.strftime('%Y-%m-%d') if current_touch else 'unverified'}")
            lines.append(f"- Cache sync: {synced_at.strftime('%Y-%m-%d %H:%M UTC') if synced_at else 'unverified'}")
            lines.append(f"- CRM stale? {'YES' if crm_stale else 'No'}")
            lines.append(f"- SharePoint stale? {'YES' if sharepoint_stale else 'No'}")
            if blocker:
                lines.append(f"- Blocker: {blocker}")
            if evidence:
                lines.append("- Evidence:")
                lines.extend(format_hit(h) for h in evidence[:5])
            else:
                lines.append("- Evidence: no recent mailbox hit in current scan window")
            if crm_stale and sharepoint_stale:
                exact_action = "Update CRM summary row and SharePoint Current file to match recent movement."
            elif crm_stale:
                exact_action = "Update CRM summary row to reflect recent movement or mark coverage incomplete if live verification is needed."
            elif sharepoint_stale:
                exact_action = "Refresh SharePoint Current file and mark CRM pending/confirmed state accordingly."
            elif blocker:
                exact_action = "Verify the intended SharePoint path or cache freshness before claiming current state."
            if exact_action:
                lines.append(f"- Exact action needed: {exact_action}")
            lines.append("")
    if stale_count == 0:
        lines.append("## Result")
        lines.append("No obvious CRM/SharePoint drift detected in the current scan window.")
        if last_scan:
            lines.append(f"Window start: {last_scan.strftime('%Y-%m-%d %H:%M UTC')}")
    if coverage_incomplete:
        lines.append("## Coverage incomplete")
        for name in coverage_incomplete:
            lines.append(f"- {name}")
    return "\n".join(lines).strip() + "\n"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "last_updated": now_utc().isoformat(),
            "schema_version": 1,
            "items": [],
        }
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict) -> None:
    state["last_updated"] = now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def load_surface_state() -> dict:
    if not SURFACE_STATE_PATH.exists():
        return {
            "last_updated": now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "schema_version": 1,
            "surfaces": {},
        }
    return json.loads(SURFACE_STATE_PATH.read_text())


def save_surface_state(state: dict) -> None:
    state["last_updated"] = now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    SURFACE_STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def _proof_safe_item(item: dict) -> dict:
    """Apply the bounded closure contract before monitored state is saved."""
    closure = item.get("closure_state")
    refs = item.get("evidence_refs") or []
    if closure == "closed" and not refs:
        item["closure_state"] = "coverage_incomplete"
        item["blocker"] = "closed state rejected: no durable evidence reference"
        item["resolved_at"] = None
    if closure in {"blocked", "coverage_incomplete", "blocked_pending_gate"} and item.get("resolved_at"):
        item["resolved_at"] = None
        item.setdefault("blocker", "resolved_at removed from blocked/incomplete item")
    source_ts = parse_iso(str(item.get("source_timestamp") or ""))
    seen_ts = parse_iso(str(item.get("seen_at") or ""))
    if source_ts and seen_ts and source_ts > seen_ts:
        item["closure_state"] = "coverage_incomplete"
        item["resolved_at"] = None
        item["blocker"] = "source timestamp is later than seen_at; observation timing is unproven"
    return item


def upsert_item(args: argparse.Namespace) -> str:
    state = load_state()
    items = state.setdefault("items", [])
    for item in items:
        if item.get("id") == args.id:
            item.update({k: v for k, v in {
                "surface": args.surface,
                "entity": args.entity,
                "thread_key": args.thread_key,
                "source_timestamp": args.source_timestamp,
                "seen_at": args.seen_at,
                "flags": [f.strip() for f in args.flags.split(",") if f.strip()] if args.flags else item.get("flags", []),
                "mode": args.mode,
                "closure_state": args.closure_state,
                "blocker": args.blocker,
                "resolved_at": args.resolved_at,
            }.items() if v is not None})
            if args.evidence_ref:
                refs = item.setdefault("evidence_refs", [])
                if args.evidence_ref not in refs:
                    refs.append(args.evidence_ref)
            _proof_safe_item(item)
            save_state(state)
            return f"Updated monitored item: {args.id}"
    new_item = {
        "id": args.id,
        "surface": args.surface,
        "entity": args.entity,
        "thread_key": args.thread_key,
        "source_timestamp": args.source_timestamp,
        "seen_at": args.seen_at or now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "flags": [f.strip() for f in args.flags.split(",") if f.strip()] if args.flags else [],
        "mode": args.mode or "watch",
        "closure_state": args.closure_state or "new",
        "blocker": args.blocker,
        "evidence_refs": [args.evidence_ref] if args.evidence_ref else [],
        "resolved_at": args.resolved_at,
    }
    items.append(_proof_safe_item(new_item))
    save_state(state)
    return f"Created monitored item: {args.id}"


def blocked_items_report() -> str:
    state = load_state()
    blocked = [
        item for item in state.get("items", [])
        if item.get("closure_state") in {"blocked_pending_gate", "coverage_incomplete"}
    ]
    lines = [
        "# Blocked / Incomplete Monitored Items",
        f"_Generated: {now_utc().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
    ]
    if not blocked:
        lines.append("No blocked or coverage-incomplete monitored items.")
        return "\n".join(lines) + "\n"
    for item in blocked:
        lines.append(f"## {item.get('id', '(no id)')}")
        lines.append(f"- Surface: {item.get('surface', 'unknown')}")
        lines.append(f"- Entity: {item.get('entity', 'n/a')}")
        lines.append(f"- Mode: {item.get('mode', 'unknown')}")
        lines.append(f"- Closure state: {item.get('closure_state', 'unknown')}")
        lines.append(f"- Seen at: {item.get('seen_at', 'unknown')}")
        if item.get('blocker'):
            lines.append(f"- Blocker: {item['blocker']}")
        refs = item.get('evidence_refs') or []
        if refs:
            lines.append("- Evidence refs:")
            lines.extend(f"  - {ref}" for ref in refs)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _read_text(path: Path) -> str:
    return path.read_text(errors="ignore") if path.exists() else ""


def _extract_last_updated(text: str) -> datetime | None:
    for line in text.splitlines()[:6]:
        cleaned = line.strip().strip("_")
        if cleaned.lower().startswith("last updated:"):
            raw = cleaned.split(":", 1)[1].strip()
        elif cleaned.lower().startswith("updated:"):
            raw = cleaned.split(":", 1)[1].strip()
        else:
            continue
        raw = raw.split(" — ", 1)[0].strip()
        for candidate in (
            raw,
            raw.replace(" UTC", "+00:00"),
            raw.replace(" GMT", "+00:00"),
            raw.replace(" BST", "+01:00"),
        ):
            dt = parse_iso(candidate)
            if dt:
                return dt
    m = LAST_UPDATED_RE.search(text)
    if not m:
        return None
    return parse_iso(m.group(1).strip())


def _log_has(needle: str) -> bool:
    return needle.lower() in _read_text(OP_LOG_PATH).lower()


def _recent_whatsapp_expense_items(state: dict) -> list[dict]:
    items = []
    for item in state.get("items", []):
        if item.get("surface") != "whatsapp_recent":
            continue
        flags = set(item.get("flags") or [])
        if "EXPENSE" not in flags:
            continue
        items.append(item)
    return items


def _finance_expense_by_source_ref(source_ref: str) -> dict | None:
    """Read the canonical SQLite expense outcome for one monitored source item.

    This intentionally does not consult the legacy Markdown ledger: a monitored
    item may close only from current finance status plus retained evidence.
    """
    if not FINANCE_DB_PATH.exists() or not source_ref:
        return None
    try:
        with sqlite3.connect(f"file:{FINANCE_DB_PATH}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT expense_id, status, evidence_ref, evidence_state, "
                "settlement_state, finance_ledger_ref, updated_at "
                "FROM expenses WHERE source_ref = ?", (source_ref,)
            ).fetchone()
            return dict(row) if row else None
    except sqlite3.Error:
        return None


def reconcile_expense_monitor_state() -> int:
    """Advance only terminal expense-monitor items from canonical SQLite proof.

    The monitor never treats legacy Markdown as current finance truth. Missing or
    non-terminal SQLite rows remain visible for review; terminal records update
    the monitoring state with their current durable evidence reference.
    """
    state = load_state()
    changed = 0
    for item in state.get("items", []):
        if "EXPENSE" not in set(item.get("flags") or []):
            continue
        canonical = _finance_expense_by_source_ref(str(item.get("id") or ""))
        if canonical is None or canonical["status"] not in {"ledger_written", "not_business", "duplicate"}:
            continue
        refs = item.setdefault("evidence_refs", [])
        # Legacy Markdown was once copied into monitored state. Remove it on
        # canonical reconciliation so it cannot be mistaken for live proof.
        legacy_refs = [ref for ref in refs if str(ref).endswith("seer-expenses.md")]
        if legacy_refs:
            item["evidence_refs"] = refs = [ref for ref in refs if ref not in legacy_refs]
            changed += len(legacy_refs)
        for ref in (canonical.get("evidence_ref"), canonical.get("finance_ledger_ref")):
            if ref and ref not in refs:
                refs.append(ref)
                changed += 1
        desired_state = "closed"
        if item.get("closure_state") != desired_state or item.get("blocker") is not None:
            item["closure_state"] = desired_state
            item["blocker"] = None
            item["resolved_at"] = canonical.get("updated_at") or now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
            changed += 1
        _proof_safe_item(item)
    if changed:
        save_state(state)
    return changed


def _read_actioned_lines() -> list[str]:
    path = WORKSPACE / "ACTIONED.md"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(errors="ignore").splitlines() if line.strip() and not line.startswith("#")]


def upsert_surface(args: argparse.Namespace) -> str:
    state = load_surface_state()
    surfaces = state.setdefault("surfaces", {})
    existing = surfaces.get(args.surface, {})
    merged = dict(existing)
    merged.update({k: v for k, v in {
        "surface": args.surface,
        "source_file": args.source_file,
        "last_check_attempt": args.last_check_attempt,
        "last_successful_check": args.last_successful_check,
        "last_successful_visible_update": args.last_successful_visible_update,
        "last_result_shape": args.last_result_shape,
        "coverage_state": args.coverage_state,
        "notes": args.notes,
    }.items() if v is not None})
    surfaces[args.surface] = merged
    save_surface_state(state)
    return f"Upserted monitoring surface state: {args.surface}"


def _ensure_surface(surface_key: str, source_file: str) -> dict:
    surface_state = load_surface_state()
    surfaces = surface_state.setdefault("surfaces", {})
    surface = surfaces.setdefault(surface_key, {
        "surface": surface_key,
        "source_file": source_file,
        "last_check_attempt": None,
        "last_successful_check": None,
        "last_successful_visible_update": None,
        "last_result_shape": None,
        "coverage_state": "blocked",
        "notes": None,
    })
    return surface_state


def _section_text(text: str, heading: str | None) -> str:
    if not heading:
        return text
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            start = idx + 1
            break
    if start is None:
        return ""
    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith("## ") and line.strip() != heading:
            break
        collected.append(line)
    return "\n".join(collected)


def _extract_latest_email_timestamp(text: str, *, heading: str | None = None) -> datetime | None:
    hits: list[datetime] = []
    scoped = _section_text(text, heading)
    for block in split_message_blocks(scoped):
        ts = parse_block_timestamp(block)
        if ts:
            hits.append(ts)
    return max(hits) if hits else None


def _extract_latest_whatsapp_timestamp(text: str) -> datetime | None:
    hits: list[datetime] = []
    for match in WHATSAPP_LINE_RE.finditer(text):
        ts = parse_iso(match.group(1))
        if ts:
            hits.append(ts)
    return max(hits) if hits else None


def _extract_latest_teams_timestamp(text: str) -> datetime | None:
    hits: list[datetime] = []
    for match in TEAMS_LINE_RE.finditer(text):
        ts = parse_iso(match.group(1).replace(" ", "T") + ":00+00:00")
        if ts:
            hits.append(ts)
    return max(hits) if hits else None


def _extract_latest_visible_timestamp(surface_key: str, text: str) -> datetime | None:
    if surface_key == "whatsapp_recent":
        return _extract_latest_whatsapp_timestamp(text)
    if surface_key == "teams_recent":
        return _extract_latest_teams_timestamp(text)
    if surface_key == "stackstone_leads":
        return _extract_last_updated(text)
    spec = SURFACE_SPECS[surface_key]
    heading = spec.get("section_heading")
    return _extract_latest_email_timestamp(text, heading=str(heading) if heading else None)


def _report_for_surface(surface_key: str, *, quiet_indicators: list[str] | None = None) -> str:
    spec = SURFACE_SPECS[surface_key]
    source_path: Path = spec["source_path"]
    text = _read_text(source_path)
    return _generic_continuity_report(
        surface_key=surface_key,
        source_path=source_path,
        title=str(spec["title"]),
        threshold_hours=int(spec["threshold_hours"]),
        latest_visible_ts=_extract_latest_visible_timestamp(surface_key, text),
        quiet_indicators=quiet_indicators,
    )


def _render_surface_report(title: str, surface: dict, user_message: str, generated_at: datetime) -> str:
    lines = [
        f"# {title}",
        f"_Generated: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Surface",
        f"- Surface: `{surface.get('surface')}`",
        f"- Last check attempt: {surface.get('last_check_attempt') or 'unverified'}",
        f"- Last successful check: {surface.get('last_successful_check') or 'unverified'}",
        f"- Last successful visible update: {surface.get('last_successful_visible_update') or 'unverified'}",
        f"- Result shape: {surface.get('last_result_shape') or 'unverified'}",
        f"- Coverage state: {surface.get('coverage_state') or 'unverified'}",
    ]
    if surface.get("notes"):
        lines.append(f"- Notes: {surface['notes']}")
    lines.extend(["", "## User-facing result", user_message, ""])
    return "\n".join(lines).rstrip() + "\n"


def _generic_continuity_report(*, surface_key: str, source_path: Path, title: str, threshold_hours: int, latest_visible_ts: datetime | None, quiet_indicators: list[str] | None = None) -> str:
    now = now_utc()
    text = _read_text(source_path)
    visible_update = _extract_last_updated(text)
    stale_cutoff = now - timedelta(hours=threshold_hours)
    surface_state = _ensure_surface(surface_key, source_path.name)
    surfaces = surface_state.setdefault("surfaces", {})
    surface = surfaces[surface_key]
    expected_source = source_path.name
    expected_section = str(SURFACE_SPECS[surface_key].get("section_heading") or "")
    owner_changed = (
        surface.get("source_file") != expected_source
        or surface.get("source_section", "") != expected_section
    )
    if owner_changed:
        # Do not trust an anchor written by a retired source owner. Preserve the
        # evidence by forcing a fresh baseline on this run.
        surface["source_file"] = expected_source
        surface["source_section"] = expected_section or None
        surface["last_successful_check"] = None
        surface["last_successful_visible_update"] = None
        surface["last_result_shape"] = "coverage_incomplete"
        surface["coverage_state"] = "incomplete"
        surface["notes"] = (
            f"Continuity source migrated to {expected_source}"
            + (f" section {expected_section}" if expected_section else "")
            + "; prior anchor invalidated and baseline re-established."
        )
    prior_anchor = None if owner_changed else parse_iso(surface.get("last_successful_visible_update"))
    surface["last_check_attempt"] = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    trusted_anchor = visible_update or prior_anchor
    if visible_update:
        surface["last_successful_visible_update"] = visible_update.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    fresh_enough = bool(visible_update and visible_update >= stale_cutoff)
    feed_reports_incomplete = "Coverage incomplete:" in text
    required_section_missing = bool(expected_section and expected_section not in text)
    quiet = bool(quiet_indicators and all(indicator in text for indicator in quiet_indicators))
    new_visible_since_prior = bool(latest_visible_ts and prior_anchor and latest_visible_ts > prior_anchor)

    if fresh_enough and not feed_reports_incomplete and not required_section_missing:
        surface["last_successful_check"] = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        surface["coverage_state"] = "clean"
        if quiet or not latest_visible_ts or (prior_anchor and latest_visible_ts and latest_visible_ts <= prior_anchor):
            surface["last_result_shape"] = "no_new_visible_activity"
            surface["notes"] = "Fresh feed with no new visible activity since the prior clean anchor."
        elif not prior_anchor:
            surface["last_result_shape"] = "no_new_visible_activity"
            surface["notes"] = "Fresh feed; baseline continuity anchor established."
        else:
            surface["last_result_shape"] = "new_visible_activity"
            surface["notes"] = "Fresh feed shows visible activity newer than the prior clean anchor."
    else:
        surface["coverage_state"] = "incomplete"
        if new_visible_since_prior:
            surface["last_result_shape"] = "mixed_visible_and_incomplete"
            surface["notes"] = "Visible new activity exists since the prior clean anchor, but the current refresh is stale/incomplete."
        else:
            surface["last_result_shape"] = "coverage_incomplete"
            if required_section_missing:
                surface["notes"] = f"Required source section {expected_section} is absent; outbound coverage is incomplete."
            elif trusted_anchor:
                surface["notes"] = f"No new visible activity since {trusted_anchor.strftime('%Y-%m-%d %H:%M UTC')}, but current refresh is stale/incomplete."
            else:
                surface["notes"] = "Current refresh is stale/incomplete and no trusted clean anchor could be established."

    save_surface_state(surface_state)

    anchor = trusted_anchor or parse_iso(surface.get("last_successful_visible_update"))
    if surface["last_result_shape"] == "no_new_visible_activity" and anchor:
        user_message = f"No new visible activity since {anchor.strftime('%Y-%m-%d %H:%M UTC')}."
    elif surface["last_result_shape"] == "new_visible_activity" and anchor:
        user_message = f"New visible activity since {anchor.strftime('%Y-%m-%d %H:%M UTC')} — review the feed contents."
    elif surface["last_result_shape"] == "mixed_visible_and_incomplete" and anchor:
        user_message = f"New visible activity since {anchor.strftime('%Y-%m-%d %H:%M UTC')}, but coverage after the latest visible refresh is incomplete."
    elif surface["last_result_shape"] == "coverage_incomplete" and anchor:
        user_message = f"No new visible activity since {anchor.strftime('%Y-%m-%d %H:%M UTC')}, but today's refresh/check did not complete so coverage after that point is incomplete."
    else:
        user_message = "Coverage incomplete: current feed state does not provide a trusted clean anchor."

    return _render_surface_report(title, surface, user_message, now)


def website_activity_continuity_report() -> str:
    return _report_for_surface(
        "stackstone_leads",
        quiet_indicators=["No new leads.", "No new packs.", "No new conversations."],
    )


def gmail_continuity_report() -> str:
    return _report_for_surface("gmail_inbox")


def microsoft_continuity_report() -> str:
    return _report_for_surface("microsoft_inbox")


def assistant_inbox_continuity_report() -> str:
    return _report_for_surface("assistant_inbox")


def assistant_external_continuity_report() -> str:
    return _report_for_surface("assistant_external")


def gmail_external_continuity_report() -> str:
    return _report_for_surface("gmail_external")


def microsoft_external_continuity_report() -> str:
    return _report_for_surface("microsoft_external")


def _load_whatsapp_retained_window() -> dict:
    """Read the renderer's loss-detection contract; missing/invalid is incomplete."""
    try:
        payload = json.loads(_read_text(WHATSAPP_WINDOW_PATH) or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def whatsapp_continuity_report() -> str:
    """Fail closed when the rolling WhatsApp view no longer covers the prior cursor."""
    window = _load_whatsapp_retained_window()
    earliest = parse_iso(window.get("earliest_retained_source_timestamp"))
    latest = parse_iso(window.get("latest_retained_source_timestamp"))
    surface_state = _ensure_surface("whatsapp_recent", WHATSAPP_RECENT_PATH.name)
    surface = surface_state.setdefault("surfaces", {})["whatsapp_recent"]
    prior_anchor = parse_iso(surface.get("last_successful_visible_update"))
    now = now_utc()
    surface["last_check_attempt"] = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if not earliest or not latest:
        surface["coverage_state"] = "incomplete"
        surface["last_result_shape"] = "coverage_incomplete"
        surface["notes"] = "WhatsApp retained-window metadata is missing or invalid; the rolling view cannot prove its coverage interval."
        save_surface_state(surface_state)
        return _render_surface_report("WhatsApp Continuity Report", surface, "Coverage incomplete: the WhatsApp rolling view has no valid retained-window proof.", now)

    if prior_anchor and prior_anchor < earliest:
        surface["coverage_state"] = "incomplete"
        surface["last_result_shape"] = "coverage_incomplete"
        surface["notes"] = (
            "The prior clean cursor predates the earliest retained WhatsApp source event; "
            f"the interval {prior_anchor.strftime('%Y-%m-%d %H:%M UTC')} to "
            f"{earliest.strftime('%Y-%m-%d %H:%M UTC')} cannot be proven from the rolling view."
        )
        # Never advance the clean anchor or mark this view seen: doing so would
        # silently discard events evicted before the current snapshot.
        save_surface_state(surface_state)
        return _render_surface_report(
            "WhatsApp Continuity Report",
            surface,
            "Coverage incomplete: the rolling WhatsApp view no longer contains the full interval after the prior clean cursor.",
            now,
        )

    report = _generic_continuity_report(
        surface_key="whatsapp_recent",
        source_path=WHATSAPP_RECENT_PATH,
        title="WhatsApp Continuity Report",
        threshold_hours=2,
        latest_visible_ts=latest,
    )
    # `_generic_continuity_report` normally uses render time as its anchor.
    # For a rolling chat feed, only the latest retained *event* proves coverage.
    refreshed = load_surface_state()
    item = refreshed.setdefault("surfaces", {}).setdefault("whatsapp_recent", {})
    if item.get("coverage_state") == "clean":
        item["last_successful_visible_update"] = latest.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        item["notes"] = "Fresh rolling view covers the prior cursor through the latest retained source event."
        save_surface_state(refreshed)
        return _render_surface_report("WhatsApp Continuity Report", item, f"No new visible activity since {latest.strftime('%Y-%m-%d %H:%M UTC')}.", now)
    return report


def teams_continuity_report() -> str:
    return _report_for_surface("teams_recent")


def classify_teams_item(item: dict) -> dict:
    """Compatibility wrapper over the central mirror router."""
    event = event_from_dict({**item, "surface": item.get("surface") or "teams_recent"})
    classified = classify_mirror_event(event, entity_candidates=load_crm_entity_candidates(CRM_PATH))
    # Preserve existing report field names while centralising classification logic.
    classified["kind"] = classified.get("source_type")
    classified["location"] = classified.get("subject_or_location")
    classified["summary"] = classified.get("body_preview")
    return classified


def surface_coverage_state(surface_key: str, surface_state: dict | None = None) -> str:
    """Return the continuity truth for a surface; missing state is never clean."""
    state = surface_state if surface_state is not None else load_surface_state()
    item = (state.get("surfaces") or {}).get(surface_key) or {}
    coverage = item.get("coverage_state") or item.get("status")
    return str(coverage or "coverage_incomplete")


def _email_events_from_surface(surface_key: str, max_items: int = 50, coverage_state: str = "coverage_incomplete") -> list[MirrorEvent]:
    spec = SURFACE_SPECS[surface_key]
    path: Path = spec["source_path"]
    heading = spec.get("section_heading")
    text = _read_text(path)
    if heading:
        marker = str(heading)
        idx = text.find(marker)
        text = text[idx:] if idx >= 0 else ""
    events: list[MirrorEvent] = []
    for block in split_message_blocks(text):
        raw = block_text(block)
        ts = parse_block_timestamp(block)
        subject = next((ln.strip("* ") for ln in block if ln.startswith("**") and ln.endswith("**")), "")
        from_line = next((ln for ln in block if ln.startswith("From:")), "")
        to_line = next((ln for ln in block if ln.startswith("To:")), "")
        msg_id = next((ln.split(":", 1)[1].strip() for ln in block if ln.startswith("Message ID:")), None)
        sender = from_line.split("|", 1)[0].replace("From:", "").strip() if from_line else ""
        recipient = to_line.split("|", 1)[0].replace("To:", "").strip() if to_line else ""
        direction = "outbound" if to_line else "inbound"
        body_preview = " ".join([ln.strip() for ln in block if not ln.startswith(("**", "From:", "To:", "Message ID:", "Conversation ID:", "Internet Message ID:"))])[:700]
        if not (subject or sender or recipient or body_preview):
            continue
        events.append(MirrorEvent(
            surface=surface_key,
            source_type="email",
            source_timestamp=ts.replace(microsecond=0).isoformat().replace("+00:00", "Z") if ts else None,
            direction=direction,
            sender=sender or recipient,
            participants=[p for p in [sender, recipient] if p],
            thread_key=next((ln.split(":", 1)[1].strip() for ln in block if ln.startswith("Conversation ID:")), None),
            source_id=msg_id or subject[:120],
            subject_or_location=subject,
            body_preview=body_preview,
            raw_evidence_ref=path.name,
            trust_class=str(spec.get("kind") or "inbound"),
            coverage_state=coverage_state,
        ))
        if len(events) >= max_items:
            break
    return events


def _whatsapp_events(max_items: int = 120, coverage_state: str = "coverage_incomplete") -> list[MirrorEvent]:
    text = _read_text(WHATSAPP_RECENT_PATH)
    events: list[MirrorEvent] = []
    current: dict | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        m = re.match(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\] (.*?):\s?(.*)$", line)
        if m:
            if current:
                current["line_end"] = line_number - 1
                events.append(_whatsapp_event_from_parts(current, coverage_state=coverage_state))
                if len(events) >= max_items:
                    break
            ts, speaker, body = m.groups()
            current = {"ts": ts, "speaker": speaker, "body": [body], "line_start": line_number, "line_end": line_number}
        elif current and line.strip():
            current["body"].append(line.strip())
            current["line_end"] = line_number
    if current:
        current["line_end"] = current.get("line_end") or len(text.splitlines())

    if current and len(events) < max_items:
        events.append(_whatsapp_event_from_parts(current, coverage_state=coverage_state))
    return events


def _whatsapp_event_from_parts(parts: dict, coverage_state: str = "coverage_incomplete") -> MirrorEvent:
    ts = parse_iso(str(parts["ts"]).replace(" ", "T") + ":00+00:00")
    speaker = str(parts["speaker"])
    body = " ".join(parts.get("body") or [])[:700]
    direction = "self" if speaker in {"Me", "Tom", "Tom Dean"} or speaker.startswith("Tom ->") else "inbound"
    source_type = "group" if speaker.startswith("[") else "direct"
    # Direct outbound transcript lines carry the recipient after `Tom ->`.
    # Preserve it as the thread/participant so central CRM mapping can use the
    # visible target rather than treating all of Tom's messages as self-only.
    recipient = speaker.split("->", 1)[1].strip() if direction == "self" and "->" in speaker else ""
    thread_key = recipient or speaker.split(":", 1)[0]
    source_line_ref = f"WHATSAPP_RECENT.md:L{parts.get('line_start', '?')}-L{parts.get('line_end', parts.get('line_start', '?'))}"
    return MirrorEvent(
        surface="whatsapp_recent",
        source_type=source_type,
        source_timestamp=ts.replace(microsecond=0).isoformat().replace("+00:00", "Z") if ts else None,
        direction=direction,
        sender="Tom" if recipient else speaker,
        participants=[participant for participant in (["Tom", recipient] if recipient else [speaker]) if participant],
        thread_key=thread_key,
        source_id=f"{parts['ts']}:{speaker}:{body[:80]}",
        subject_or_location=thread_key,
        body_preview=body,
        raw_evidence_ref=source_line_ref,
        trust_class="chat",
        coverage_state=coverage_state,
        metadata={"source_line_ref": source_line_ref, "visible_speaker": speaker},
    )


def _website_intake_events(max_items: int = 100, coverage_state: str = "coverage_incomplete") -> list[MirrorEvent]:
    """Read explicitly embedded canonical website fixture/adapter records only.

    The lead mirror remains human-readable Markdown; only ``<!-- intake-event:
    {...} -->`` records are admitted. Free text is never guessed into a source
    identity, preserving the receipt-safe contract.
    """
    text = _read_text(STACKSTONE_LEADS_PATH)
    events: list[MirrorEvent] = []
    for raw in re.findall(r"<!--\s*intake-event\s*:\s*(\{.*?\})\s*-->", text, re.S | re.I):
        try:
            item = json.loads(raw)
            if not isinstance(item, dict):
                continue
            item.setdefault("coverage_state", coverage_state)
            events.append(normalize_website_intake_item(item))
        except (json.JSONDecodeError, TypeError):
            # A malformed embedded record cannot be safely turned into a lead.
            continue
        if len(events) >= max_items:
            break
    return events

def _classify_canonical_event(event: MirrorEvent, *, entity_candidates: list[tuple[str, list[str]]], recent_outbound_addresses: set[str], live_entity_types: dict[str, str]) -> dict:
    if event.surface == "stackstone_leads":
        proposed = classify_website_intake_item({
            "provider_event_id": event.source_id, "provider_conversation_id": event.thread_key,
            "source_timestamp": event.source_timestamp, "sender": event.sender,
            "participants": event.participants, "subject": event.subject_or_location,
            "body_preview": event.body_preview, "raw_evidence_ref": event.raw_evidence_ref,
            "coverage_state": event.coverage_state, "request_type": event.source_type,
        })
        adapter_fields = {key: value for key, value in proposed.items() if key not in {"event", "event_dict"}}
        return {**event_to_dict(event), **adapter_fields,
            "stable_item_key": event.stable_item_key, "surface": event.surface, "source_type": event.source_type,
            "source_timestamp": event.source_timestamp, "sender": event.sender, "subject_or_location": event.subject_or_location,
            "body_preview": event.body_preview, "thread_key": event.thread_key, "source_id": event.source_id,
            "management_relevance": "needs_management" if proposed["closure_state"] == "review_pending" else "coverage_incomplete",
            "owning_system": "alert" if proposed["closure_state"] == "review_pending" else "none",
            "required_next_action": "Review receipt-safe website intake across alert, CRM and SharePoint; do not write before attribution review.",
            "route_state": "proposed" if proposed["closure_state"] == "review_pending" else "coverage_incomplete",
            "candidate_entities": [], "routing_flags": ["ALERT", "CRM"] if proposed["closure_state"] == "review_pending" else [],
            "proof_source": event.raw_evidence_ref, "reasons": [proposed.get("review_reason", "website intake review required")],
        }
    return classify_mirror_event(event, entity_candidates=entity_candidates, recent_outbound_addresses=recent_outbound_addresses, live_entity_types=live_entity_types)

def build_canonical_mirror_events(surface_keys: list[str] | None = None) -> list[MirrorEvent]:
    selected = surface_keys or ["stackstone_leads", *FIRST_CLASS_INTAKE_SURFACES, *OUTBOUND_CONTEXT_SURFACES]
    surface_state = load_surface_state()
    events: list[MirrorEvent] = []
    for surface_key in selected:
        coverage_state = surface_coverage_state(surface_key, surface_state)
        if surface_key == "stackstone_leads":
            events.extend(_website_intake_events(coverage_state=coverage_state))
        elif surface_key == "teams_recent":
            try:
                payload = json.loads(_read_text(TEAMS_RECENT_JSON_PATH) or "{}")
                payload_coverage = payload.get("coverage_state") or "coverage_incomplete"
                for raw in payload.get("items") or []:
                    event = event_from_dict(raw)
                    event.coverage_state = "coverage_incomplete" if "coverage_incomplete" in {coverage_state, payload_coverage, event.coverage_state} else coverage_state
                    events.append(event)
            except json.JSONDecodeError:
                events.append(MirrorEvent(surface="teams_recent", source_type="feed", coverage_state="coverage_incomplete", body_preview="Invalid Teams JSON feed"))
        elif surface_key == "whatsapp_recent":
            events.extend(_whatsapp_events(coverage_state=coverage_state))
        elif surface_key in SURFACE_SPECS and SURFACE_SPECS[surface_key].get("kind") in {"inbound", "outbound"}:
            events.extend(_email_events_from_surface(surface_key, coverage_state=coverage_state))
    return events


def load_mirror_router_state() -> dict:
    if not MIRROR_ROUTER_STATE_PATH.exists():
        return {"seen": {}, "last_run_at": None}
    try:
        return json.loads(MIRROR_ROUTER_STATE_PATH.read_text(errors="ignore") or "{}")
    except json.JSONDecodeError:
        return {"seen": {}, "last_run_at": None, "state_error": "invalid_json"}


def save_mirror_router_state(state: dict) -> None:
    state["last_run_at"] = now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    MIRROR_ROUTER_STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def _event_key(event: MirrorEvent) -> str:
    return event.stable_item_key


def _filter_unseen_events(events: list[MirrorEvent], router_state: dict) -> list[MirrorEvent]:
    seen = router_state.setdefault("seen", {})
    return [event for event in events if _event_key(event) not in seen]


def _mark_events_seen(events: list[MirrorEvent], router_state: dict) -> None:
    seen = router_state.setdefault("seen", {})
    stamped = now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for event in events:
        seen[_event_key(event)] = {
            "surface": event.surface,
            "source_timestamp": event.source_timestamp,
            "first_seen_at": seen.get(_event_key(event), {}).get("first_seen_at", stamped),
            "last_seen_at": stamped,
        }
    # Keep dedupe state bounded per surface; durable closure proof belongs in the ledger.
    by_surface: dict[str, list[tuple[str, dict]]] = {}
    for key, value in seen.items():
        by_surface.setdefault(str(value.get("surface") or "unknown"), []).append((key, value))
    for entries in by_surface.values():
        entries.sort(key=lambda pair: str(pair[1].get("last_seen_at") or ""), reverse=True)
        for key, _ in entries[MAX_SEEN_EVENTS_PER_SURFACE:]:
            seen.pop(key, None)


def migrate_identityless_router_state(*, write: bool = False) -> dict:
    """Expose legacy no-ID seen keys as durable coverage defects exactly once.

    Old router runs marked synthetic ``no-thread:no-source-id`` keys as seen.
    They can never support a route receipt, so preserve the coverage gap in the
    monitored-item ledger rather than re-admitting them to any workflow.
    """
    router_state = load_mirror_router_state()
    seen = router_state.setdefault("seen", {})
    state = load_state()
    ledger_items = state.setdefault("items", [])
    by_id = {str(item.get("id")): item for item in ledger_items if item.get("id")}
    stamped = now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    migrated: list[str] = []

    for key, seen_entry in seen.items():
        if not key.endswith(":no-thread:no-source-id"):
            continue
        migrated.append(key)
        existing = by_id.get(key)
        if existing is None:
            existing = {
                "id": key,
                "surface": seen_entry.get("surface") or key.split(":", 1)[0],
                "source_timestamp": seen_entry.get("source_timestamp"),
                "seen_at": seen_entry.get("last_seen_at") or stamped,
                "mode": "watch",
                "management_relevance": "coverage_incomplete",
                "owning_system": "none",
                "required_next_action": "Restore a provider item or conversation identifier before routing",
                "route_state": "coverage_incomplete",
                "closure_state": "coverage_incomplete",
                "blocker": "legacy router seen key lacks both provider item ID and conversation/thread ID",
                "evidence_refs": ["memory/mirror-router-state.json"],
                "identity_state": "coverage_incomplete",
                "first_routed_at": stamped,
                "last_routed_at": stamped,
            }
            ledger_items.append(existing)
            by_id[key] = existing
        else:
            existing.update({
                "management_relevance": "coverage_incomplete",
                "owning_system": "none",
                "required_next_action": "Restore a provider item or conversation identifier before routing",
                "route_state": "coverage_incomplete",
                "closure_state": "coverage_incomplete",
                "blocker": "legacy router seen key lacks both provider item ID and conversation/thread ID",
                "identity_state": "coverage_incomplete",
            })
            existing.setdefault("evidence_refs", ["memory/mirror-router-state.json"])
        seen_entry["identity_state"] = "coverage_incomplete"
        seen_entry["migration_state"] = "legacy_identityless_preserved"
        seen_entry.setdefault("migrated_at", stamped)

    if write and migrated:
        save_state(state)
        save_mirror_router_state(router_state)
    return {"matched": len(migrated), "keys": migrated, "written": bool(write and migrated)}


def persist_canonical_intake_ledger(events: list[MirrorEvent], classified: list[dict], now: datetime, *, ledger_root: Path = WORKSPACE / "memory") -> None:
    """Write canonical event and pending/coverage receipts without dispatching work.

    This is the active router-to-ledger boundary. Destination workers retain their
    own approval gates and may advance only their matching receipt row.
    """
    observed_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for event, item in zip(events, classified):
        if not event.has_receipt_safe_identity:
            continue
        relevance = str(item.get("management_relevance") or "unassessed")
        # Some canonical adapters deliberately require several independent
        # review receipts (website intake: alert + CRM + SharePoint).  Preserve
        # that declared review set instead of collapsing it to a primary owner.
        declared_routes = item.get("route_set") or []
        route_set: list[str] = [str(route) for route in declared_routes if str(route).strip()]
        if relevance == "needs_management" and not route_set:
            owner = str(item.get("owning_system") or "none")
            if owner and owner != "none":
                route_set.append(owner)
        if event.coverage_state != "clean" or relevance == "coverage_incomplete":
            route_set.append("coverage")
        route_set = sorted(set(route_set))
        canonical, _ = record_intake_event({
            "surface": event.surface,
            "provider_event_id": event.source_id,
            "provider_conversation_id": event.thread_key,
            "source_timestamp": event.source_timestamp,
            "observed_at": observed_at,
            "evidence_refs": [event.raw_evidence_ref] if event.raw_evidence_ref else [],
            "identity_state": "receipt_safe",
            "classification": relevance,
            "confidence": "policy",
            "entity_state": "mapped" if item.get("candidate_entities") else "unmapped",
            "entity_refs": item.get("candidate_entities") or [],
            "route_set": route_set,
        }, root=ledger_root)
        for route in route_set:
            coverage = route == "coverage"
            record_intake_receipt({
                "event_id": canonical["event_id"],
                "route": route,
                "state": "coverage_incomplete" if coverage else "pending",
                "owner": "monitoring" if coverage else route,
                "evidence_ref": event.raw_evidence_ref or None,
                "destination_ref": None,
                "error_code": "source_coverage_incomplete" if coverage else None,
                "next_review_at": observed_at if coverage else None,
            }, root=ledger_root)


def build_intake_action_manifest(classified: list[dict], now: datetime) -> dict:
    """Upsert actionable mirror handoffs; do not erase unresolved work on a quiet pass."""
    generated_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    existing: dict[str, dict] = {}
    try:
        prior = json.loads(INTAKE_ACTIONS_PATH.read_text())
        existing = {str(action.get("id")): action for action in prior.get("actions", []) if action.get("id")}
    except (OSError, json.JSONDecodeError, AttributeError):
        pass

    for item in classified:
        if item.get("route_state") not in {"proposed", "blocked", "coverage_incomplete"}:
            continue
        action_id = str(item.get("stable_item_key"))
        prior = existing.get(action_id, {})
        existing[action_id] = {
            "id": action_id,
            "owner": item.get("owning_system"),
            "required_next_action": item.get("required_next_action"),
            "route_state": item.get("route_state"),
            "flags": item.get("routing_flags") or [],
            "evidence_ref": item.get("proof_source"),
            "source_timestamp": item.get("source_timestamp"),
            "candidate_entities": item.get("candidate_entities") or [],
            "first_routed_at": prior.get("first_routed_at", generated_at),
            "last_routed_at": generated_at,
            "fulfilment_state": prior.get("fulfilment_state", "pending"),
            "fulfilment_proof": prior.get("fulfilment_proof"),
        }
    actions = sorted(existing.values(), key=lambda action: (str(action.get("fulfilment_state")) in {"verified", "closed"}, str(action.get("source_timestamp") or "")), reverse=False)
    return {"generated_at": generated_at, "schema_version": 2, "actions": actions}


def _health_timestamp(value: str | None) -> str | None:
    """Normalize a persisted health timestamp without inventing a cursor."""
    parsed = parse_iso(value)
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z") if parsed else None


def _surface_health_coverage(surface: dict | None) -> tuple[str, str | None]:
    """Map continuity state into the ledger's deliberately smaller fail-closed set."""
    if not surface:
        return "coverage_incomplete", "No continuity state has been recorded for this surface."
    raw = str(surface.get("coverage_state") or "").lower()
    if raw == "clean":
        return "clean", None
    if raw == "blocked":
        return "blocked", str(surface.get("notes") or "Surface continuity is blocked.")
    return "coverage_incomplete", str(surface.get("notes") or "Surface continuity is incomplete or unverified.")


def _upsert_mirror_surface_health(
    *,
    surface_keys: list[str],
    all_events: list[MirrorEvent],
    routed_events: list[MirrorEvent],
    classified: list[dict],
    attempted_at: datetime,
    duration_ms: int,
    ledger_root: Path = WORKSPACE / "memory",
) -> None:
    """Persist one bounded, fail-closed intake-health row per included surface.

    This is intentionally an observation receipt, not destination proof: routing
    does not promote an item to verified simply because it was classified.
    """
    surface_state = load_surface_state().get("surfaces") or {}
    included = [key for key in surface_keys if key in ALL_MONITORED_SURFACES]
    for surface_key in dict.fromkeys(included):
        continuity = surface_state.get(surface_key)
        coverage_state, continuity_error = _surface_health_coverage(continuity)
        visible = [event for event in all_events if event.surface == surface_key]
        routed = [event for event in routed_events if event.surface == surface_key]
        classified_for_surface = [
            item for event, item in zip(routed_events, classified)
            if event.surface == surface_key
        ]
        blocker_candidates = [
            item for item in classified_for_surface
            if item.get("route_state") in {"blocked", "coverage_incomplete"}
            or item.get("closure_state") in {"blocked", "coverage_incomplete"}
        ]
        blocker_candidates.sort(key=lambda item: str(item.get("source_timestamp") or ""))
        oldest = blocker_candidates[0] if blocker_candidates else None
        source_timestamps = [parse_iso(event.source_timestamp) for event in visible]
        watermark = max((stamp for stamp in source_timestamps if stamp), default=None)
        last_visible = _health_timestamp(str((continuity or {}).get("last_successful_visible_update") or ""))
        last_successful_attempt = _health_timestamp(str((continuity or {}).get("last_successful_check") or ""))
        blocker = None if oldest is None else {
            "stable_item_key": oldest.get("stable_item_key"),
            "source_timestamp": oldest.get("source_timestamp"),
            "reason": oldest.get("blocker") or "; ".join(oldest.get("reasons") or []) or "routing is blocked or coverage is incomplete",
        }
        update_intake_surface_health(surface_key, {
            "cadence": f"PT{SURFACE_SPECS[surface_key]['threshold_hours']}H",
            "last_successful_visible_update": last_visible,
            "watermark": watermark.replace(microsecond=0).isoformat().replace("+00:00", "Z") if watermark else None,
            "last_attempt": attempted_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "last_successful_attempt": last_successful_attempt,
            "captured_count": len(visible),
            "routed_count": len(routed),
            "verified_count": 0,
            "blocked_count": len(blocker_candidates),
            "duplicate_count": max(0, len(visible) - len(routed)),
            "oldest_blocker": blocker,
            "last_error": continuity_error,
            "runtime_duration_ms": max(0, duration_ms),
            "coverage_state": coverage_state,
        }, root=ledger_root)


def mirror_routing_report(surface_keys: list[str] | None = None, write_json: bool = False, write_state: bool = False, only_new: bool = False, mark_seen: bool = False) -> str:
    started = time.monotonic()
    now = now_utc()
    all_events = build_canonical_mirror_events(surface_keys)
    router_state = load_mirror_router_state()
    events = _filter_unseen_events(all_events, router_state) if only_new else all_events
    entity_candidates = load_crm_entity_candidates(CRM_PATH)
    live_entity_types = load_live_crm_entity_types(CRM_PATH)
    # External subject-only messages need bounded relationship context without
    # searching a mailbox: the current Sent Items slices are already in this
    # event set. This set is evidence for draft admission only, never permission
    # to send or to promote a sender.
    recent_outbound_addresses = {
        match.group(0).lower()
        for event in all_events
        if event.direction == "outbound" and event.surface in OUTBOUND_CONTEXT_SURFACES
        for match in re.finditer(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", event.sender, re.I)
    }
    # The handoff worker consumes mirror-events.json, so it must receive the
    # classification contract—not the earlier raw/unclassified event shape.
    # Preserve raw event fields (including raw_evidence_ref) alongside the
    # classification result so downstream task packets retain exact evidence.
    classified = [
        _classify_canonical_event(
            event,
            entity_candidates=entity_candidates,
            recent_outbound_addresses=recent_outbound_addresses,
            live_entity_types=live_entity_types,
        )
        for event in events
    ]
    payload = {
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "surfaces": surface_keys or list(FIRST_CLASS_INTAKE_SURFACES) + list(OUTBOUND_CONTEXT_SURFACES),
        "mode": "only_new" if only_new else "all_visible",
        "visible_event_count": len(all_events),
        "routed_event_count": len(events),
        "items": [{**event_to_dict(event), **item} for event, item in zip(events, classified)],
    }
    if write_json:
        MIRROR_EVENTS_JSON_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    if write_state:
        _upsert_mirror_surface_health(
            surface_keys=payload["surfaces"],
            all_events=all_events,
            routed_events=events,
            classified=classified,
            attempted_at=now,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        persist_canonical_intake_ledger(events, classified, now)
        manifest = build_intake_action_manifest(classified, now)
        INTAKE_ACTIONS_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
        _upsert_classified_items_to_state(classified, now, default_evidence=["memory/mirror-events.json", "memory/intake-actions.json"])
    if mark_seen or write_state:
        # A rolling WhatsApp snapshot with incomplete continuity may omit older
        # unseen messages. Never convert its currently visible subset into a
        # seen baseline until the retained-window contract proves completeness.
        markable_events = [
            event for event in all_events
            if event.surface != "whatsapp_recent" or event.coverage_state == "clean"
        ]
        _mark_events_seen(markable_events, router_state)
        save_mirror_router_state(router_state)
    lines = [
        "# Mirror Routing Report",
        f"_Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Scope",
        f"- Surfaces: {', '.join(payload['surfaces'])}",
        f"- Mode: {payload['mode']}",
        f"- Visible events: {payload['visible_event_count']}",
        f"- Routed events: {payload['routed_event_count']}",
        "- Router: `scripts/mirror_router.py`", 
        "",
        "## Managed items",
    ]
    managed = [item for item in classified if item.get("management_relevance") == "needs_management"]
    if not managed:
        lines.append("No management-worthy mirror items classified in this pass.")
    for item in managed[:80]:
        lines.extend(_render_classified_item_lines(item))
    suppressed = len(classified) - len(managed)
    lines.extend(["", "## Suppressed / not needed", f"- Count: {suppressed}"])
    return "\n".join(lines).rstrip() + "\n"


def _upsert_classified_items_to_state(classified: list[dict], now: datetime, default_evidence: list[str]) -> None:
    state = load_state()
    ledger_items = state.setdefault("items", [])
    by_id = {entry.get("id"): entry for entry in ledger_items}
    for item in classified:
        if item.get("management_relevance") != "needs_management":
            continue
        item_id = item.get("stable_item_key")
        if not item_id:
            continue
        data = {
            "id": item_id,
            "surface": item.get("surface"),
            "entity": ", ".join(item.get("candidate_entities") or []) or None,
            "thread_key": item.get("thread_key"),
            "source_timestamp": item.get("source_timestamp"),
            "seen_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "flags": item.get("routing_flags") or [],
            "mode": "watch",
            "management_relevance": item.get("management_relevance"),
            "owning_system": item.get("owning_system"),
            "required_next_action": item.get("required_next_action"),
            "route_state": item.get("route_state"),
            "closure_state": item.get("closure_state") or "classified",
            "blocker": "protected full-read gate / TOTP required before drafting" if item.get("draft_mode") == "gated_full_read" else None,
            "evidence_refs": default_evidence,
            "reply_likelihood": item.get("reply_likelihood"),
            "draft_mode": item.get("draft_mode"),
            "readability_strength": item.get("readability_strength"),
            "promotion_candidate": item.get("promotion_candidate"),
            "promotion_reason": item.get("promotion_reason"),
            "task_system_candidate": item.get("task_system_candidate"),
            "task_system_reason": item.get("task_system_reason"),
        }
        entry = by_id.get(item_id)
        if entry:
            entry.update({k: v for k, v in data.items() if v is not None})
        else:
            ledger_items.append(data)
    save_state(state)


def _render_classified_item_lines(item: dict) -> list[str]:
    lines = [
        f"### {item.get('surface')} / {item.get('source_type')} — {item.get('subject_or_location') or 'unknown'}",
        f"- Stable key: `{item.get('stable_item_key')}`",
        f"- Source timestamp: {item.get('source_timestamp')}",
        f"- Sender: {item.get('sender') or 'Unknown'}",
        f"- Management relevance: `{item.get('management_relevance')}`",
        f"- Flags: {', '.join(item.get('routing_flags') or []) or 'none'}",
        f"- Candidate entities: {', '.join(item.get('candidate_entities') or []) or 'none'}",
        f"- Closure state: `{item.get('closure_state')}`",
        f"- Reasons: {'; '.join(item.get('reasons') or []) or 'none'}",
    ]
    if item.get('reply_likelihood') and item.get('reply_likelihood') != 'none':
        lines.append(f"- Reply likelihood: `{item.get('reply_likelihood')}`")
    if item.get('draft_mode') and item.get('draft_mode') != 'none':
        lines.append(f"- Draft mode: `{item.get('draft_mode')}`")
    if item.get('readability_strength') and item.get('readability_strength') != 'n/a':
        lines.append(f"- Readability strength: `{item.get('readability_strength')}`")
    if item.get('task_system_candidate'):
        lines.append(f"- Task-system candidate: yes — {item.get('task_system_reason') or 'context-heavy reply path'}")
    if item.get('promotion_candidate'):
        lines.append(f"- Approved-sender promotion candidate: yes — {item.get('promotion_reason') or 'external consequential sender'}")
    lines.extend([
        f"- Preview: {item.get('body_preview') or '[no text]'}",
        "",
    ])
    return lines


def teams_routing_report(write_state: bool = False) -> str:
    now = now_utc()
    try:
        payload = json.loads(_read_text(TEAMS_RECENT_JSON_PATH) or "{}")
    except json.JSONDecodeError as exc:
        payload = {"surface": "teams_recent", "coverage_state": "coverage_incomplete", "errors": [f"Invalid JSON feed: {exc}"], "items": []}
    items = payload.get("items") or []
    classified = [classify_teams_item(item) for item in items]
    if write_state:
        state = load_state()
        ledger_items = state.setdefault("items", [])
        by_id = {entry.get("id"): entry for entry in ledger_items}
        for item in classified:
            if item["management_relevance"] != "needs_management":
                continue
            item_id = item.get("stable_item_key")
            if not item_id:
                continue
            entry = by_id.get(item_id)
            data = {
                "id": item_id,
                "surface": "teams_recent",
                "entity": ", ".join(item.get("candidate_entities") or []) or None,
                "thread_key": item.get("thread_key"),
                "source_timestamp": item.get("source_timestamp"),
                "seen_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "flags": item.get("routing_flags") or [],
                "mode": "watch",
                "management_relevance": item.get("management_relevance"),
                "closure_state": "classified",
                "blocker": None,
                "evidence_refs": ["memory/teams-recent.json", "TEAMS_RECENT.md"],
            }
            if entry:
                entry.update({k: v for k, v in data.items() if v is not None})
            else:
                ledger_items.append(data)
        save_state(state)
    lines = [
        "# Teams Routing Report",
        f"_Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Feed",
        f"- Source: `memory/teams-recent.json`",
        f"- Generated at: {payload.get('generated_at') or 'unknown'}",
        f"- Coverage state: {payload.get('coverage_state') or 'unknown'}",
        f"- Items: {len(items)}",
        "",
        "## Classified items",
    ]
    if not classified:
        lines.append("No Teams items to classify.")
    for item in classified:
        lines.extend([
            f"### {item.get('kind')} — {item.get('location') or 'unknown location'}",
            f"- Stable key: `{item.get('stable_item_key')}`",
            f"- Source timestamp: {item.get('source_timestamp')}",
            f"- Sender: {item.get('sender') or 'Unknown'}",
            f"- Management relevance: `{item.get('management_relevance')}`",
            f"- Flags: {', '.join(item.get('routing_flags') or []) or 'none'}",
            f"- Candidate entities: {', '.join(item.get('candidate_entities') or []) or 'none'}",
            f"- Closure state: `{item.get('closure_state')}`",
            f"- Reasons: {'; '.join(item.get('reasons') or []) or 'none'}",
            f"- Summary: {item.get('summary') or '[no text]'}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def assistant_sent_continuity_report() -> str:
    return _report_for_surface("assistant_sent")


def gmail_sent_continuity_report() -> str:
    return _report_for_surface("gmail_sent")


def microsoft_sent_continuity_report() -> str:
    return _report_for_surface("microsoft_sent")


def monitoring_surface_audit_report() -> str:
    now = now_utc()
    lines = [
        "# Monitoring Surface Audit",
        f"_Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Purpose",
        "Show which monitored surfaces are continuity-covered, stale, missing, or currently unsupported.",
        "",
    ]

    surface_state = load_surface_state().get("surfaces", {})
    item_surfaces = sorted({
        str(item.get("surface"))
        for item in load_state().get("items", [])
        if item.get("surface")
    })

    statuses: list[tuple[str, str, list[str]]] = []

    for surface_key in ALL_MONITORED_SURFACES:
        spec = SURFACE_SPECS.get(surface_key)
        state = surface_state.get(surface_key)
        if spec is None:
            statuses.append((
                "blocked",
                surface_key,
                ["First-class intake surface has no runtime spec."],
            ))
            continue
        if not spec["source_path"].exists():
            statuses.append((
                "blocked",
                surface_key,
                [f"Configured source file is missing: {spec['source_path'].name}"],
            ))
            continue
        if not state:
            statuses.append((
                "coverage incomplete",
                surface_key,
                ["Surface is part of the first-class intake set but no continuity state has been written yet."],
            ))
            continue
        expected_source = spec["source_path"].name
        expected_section = str(spec.get("section_heading") or "")
        owner_mismatch = (
            state.get("source_file") != expected_source
            or state.get("source_section", "") != expected_section
        )
        if owner_mismatch:
            statuses.append((
                "coverage incomplete",
                surface_key,
                [
                    f"Persisted continuity owner is {state.get('source_file') or 'unverified'}"
                    + (f" / {state.get('source_section')}" if state.get('source_section') else "")
                    + f"; live owner is {expected_source}"
                    + (f" / {expected_section}" if expected_section else "")
                    + ".",
                ],
            ))
            continue
        source_refresh = _extract_last_updated(_read_text(spec["source_path"]))
        last_check = parse_iso(str(state.get("last_successful_check") or ""))
        if source_refresh and (not last_check or source_refresh > last_check):
            statuses.append((
                "coverage incomplete",
                surface_key,
                [
                    f"Source refreshed at {source_refresh.isoformat()} after the last continuity check "
                    f"({state.get('last_successful_check') or 'unverified'}); current coverage is not yet proven.",
                ],
            ))
            continue
        coverage = state.get("coverage_state") or "unverified"
        result_shape = state.get("last_result_shape") or "unverified"
        last_visible = state.get("last_successful_visible_update") or "unverified"
        last_check = state.get("last_successful_check") or "unverified"
        label = "working" if coverage == "clean" else ("coverage incomplete" if coverage == "incomplete" else "blocked")
        statuses.append((
            label,
            surface_key,
            [
                f"coverage_state={coverage}",
                f"last_result_shape={result_shape}",
                f"last_successful_visible_update={last_visible}",
                f"last_successful_check={last_check}",
            ],
        ))

    extra_item_surfaces = [surface for surface in item_surfaces if surface not in ALL_MONITORED_SURFACES]
    for surface_key in extra_item_surfaces:
        if surface_key in SURFACE_SPECS:
            state = surface_state.get(surface_key)
            if state:
                statuses.append((
                    "working" if state.get("coverage_state") == "clean" else "coverage incomplete",
                    surface_key,
                    [
                        "Surface appears in monitored item state and has continuity support.",
                        f"coverage_state={state.get('coverage_state') or 'unverified'}",
                        f"last_result_shape={state.get('last_result_shape') or 'unverified'}",
                    ],
                ))
            else:
                statuses.append((
                    "coverage incomplete",
                    surface_key,
                    ["Surface appears in monitored item state but continuity state has not been written yet."],
                ))
        else:
            statuses.append((
                "blocked",
                surface_key,
                [
                    "Surface appears in monitored item state but has no continuity spec yet.",
                    "This means the system can track item-level lifecycle on this surface without proving feed-level coverage.",
                ],
            ))

    grouped_order = ["blocked", "coverage incomplete", "working"]
    grouped = {key: [] for key in grouped_order}
    for status, surface_key, bullets in statuses:
        grouped.setdefault(status, []).append((surface_key, bullets))

    for status in grouped_order:
        items = grouped.get(status) or []
        if not items:
            continue
        lines.append(f"## {status}")
        for surface_key, bullets in sorted(items, key=lambda item: item[0]):
            lines.append(f"### {surface_key}")
            lines.extend(f"- {bullet}" for bullet in bullets)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def proof_layer_reconciliation() -> str:
    reconcile_expense_monitor_state()
    now = now_utc()
    lines = [
        "# Proof-Layer Reconciliation",
        f"_Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Scope",
        "Cross-check surface continuity state, monitored item state, operational log, ACTIONED suppression, and selected destination-truth layers.",
        "",
    ]

    surface_state = load_surface_state().get("surfaces", {})
    item_state = load_state().get("items", [])
    op_log_text = _read_text(OP_LOG_PATH)
    actioned_lines = _read_actioned_lines()
    findings: list[tuple[str, str, list[str]]] = []

    for surface_key in ("stackstone_leads", *ALL_MONITORED_SURFACES):
        surface = surface_state.get(surface_key)
        if not surface:
            findings.append((
                "blocked",
                f"Missing continuity state — {surface_key}",
                ["Surface continuity state is missing; recurring monitoring cannot prove clean vs incomplete coverage for this surface."],
            ))
            continue
        result_shape = surface.get("last_result_shape")
        coverage = surface.get("coverage_state")
        anchor = surface.get("last_successful_visible_update")
        source_text = _read_text(SURFACE_SPECS.get(surface_key, {}).get("source_path", Path(""))) if surface_key in SURFACE_SPECS else ""
        latest_source = _extract_latest_visible_timestamp(surface_key, source_text) if source_text else None
        anchor_dt = parse_iso(str(anchor or ""))
        if coverage == "clean" and latest_source and anchor_dt and latest_source > anchor_dt:
            findings.append((
                "coverage_incomplete",
                f"Continuity anchor behind source — {surface_key}",
                [f"Source visibly reaches {latest_source.isoformat()} but the clean anchor is {anchor}; clean coverage is not proven."],
            ))
        if coverage == "clean" and not anchor:
            findings.append((
                "blocked",
                f"Continuity state invalid — {surface_key}",
                ["Surface is marked clean but has no last_successful_visible_update anchor."],
            ))
        elif coverage == "incomplete" and result_shape not in {"coverage_incomplete", "mixed_visible_and_incomplete"}:
            findings.append((
                "coverage_incomplete",
                f"Continuity/result mismatch — {surface_key}",
                [f"Coverage state is `{coverage}` but result shape is `{result_shape}`."],
            ))
        elif coverage == "clean" and result_shape not in {"no_new_visible_activity", "new_visible_activity"}:
            findings.append((
                "coverage_incomplete",
                f"Continuity/result mismatch — {surface_key}",
                [f"Coverage state is `{coverage}` but result shape is `{result_shape}`."],
            ))

    for item in item_state:
        closure = item.get("closure_state")
        refs = set(item.get("evidence_refs") or [])
        item_id = item.get("id", "(no id)")
        entity = item.get("entity") or "unknown entity"
        if closure == "closed":
            if not refs:
                findings.append((
                    "blocked",
                    f"Closed item missing evidence refs — {item_id}",
                    [f"Item for {entity} is marked closed but has no durable evidence refs."],
                ))
            if item.get("surface") == "whatsapp_recent" and "EXPENSE" in set(item.get("flags") or []):
                canonical = _finance_expense_by_source_ref(str(item.get("id") or ""))
                if canonical is None or canonical["status"] not in {"ledger_written", "not_business", "duplicate"}:
                    findings.append((
                        "blocked",
                        f"Closed WhatsApp expense lacks canonical SQLite proof — {item_id}",
                        [
                            f"Item for {entity} is marked closed, but canonical SQLite status is `{canonical.get('status') if canonical else 'missing'}`.",
                            "The legacy Markdown archive is not a valid closure source.",
                        ],
                    ))
        if closure in {"blocked", "coverage_incomplete"} and item.get("resolved_at"):
            findings.append((
                "coverage_incomplete",
                f"Blocked/incomplete item has resolved_at set — {item_id}",
                [f"Item for {entity} is `{closure}` but also carries resolved_at={item.get('resolved_at')}."],
            ))

        source_dt = parse_iso(str(item.get("source_timestamp") or ""))
        seen_dt = parse_iso(str(item.get("seen_at") or ""))
        if source_dt and seen_dt and source_dt > seen_dt:
            findings.append((
                "coverage_incomplete",
                f"Observation timing invalid — {item_id}",
                [f"source_timestamp={item.get('source_timestamp')} is later than seen_at={item.get('seen_at')}; closure timing is unproven."],
            ))
        if closure in {"blocked", "coverage_incomplete"} and {"ALERT", "CRM", "FOLLOW_UP"}.intersection(set(item.get("flags") or [])):
            evidence_key = item_id.lower()
            entity_key = str(entity).lower()
            if evidence_key not in op_log_text.lower() and entity_key not in op_log_text.lower():
                findings.append((
                    "destination changed but log missing",
                    f"Material blocked item absent from operational log — {item_id}",
                    [f"{entity} is materially blocked/incomplete but neither its item ID nor entity name appears in the operational activity log."],
                ))

    tracker_text = _read_text(INVOICE_TRACKER_PATH)
    tracker_json_text = _read_text(WORKSPACE / "INVOICE_TRACKER.json")
    if "INV-076" in tracker_text and "generated and stored" in op_log_text.lower():
        inv_076_has_link = "2026-06-18%20-%20Invoice%20-%20INV-076.pdf" in tracker_json_text or "2026-06-18 - Invoice - INV-076.pdf" in tracker_json_text
        inv_076_is_draft = "| INV-076 | Croyde Medical | Draft |" in tracker_text
        if not inv_076_has_link:
            findings.append((
                "coverage_incomplete",
                "INV-076 tracker mirror missing invoice-link propagation",
                ["Operational log says INV-076 was generated/stored and tracker link was updated, but the local tracker mirror does not show the stored invoice link."],
            ))
        elif inv_076_is_draft:
            findings.append((
                "logged and aligned",
                "INV-076 tracker mirror consistent with draft-stage generation",
                ["INV-076 is still Draft in the tracker mirror, but the invoice link is present. This reads as generated-and-stored without evidence that the tracker status itself should already be Sent."],
            ))

    if "Markets Recon" in _read_text(CRM_PATH) and "sp-mr-622a" in _read_text(WORKSPACE.parent / "sharepoint-queue.json") and "Markets Recon project pause captured" in op_log_text:
        findings.append((
            "logged and aligned",
            "Markets Recon queued CRM/SharePoint update",
            ["CRM was updated locally, SharePoint writes are queued, and the operational log records the queued state."],
        ))

    for line in actioned_lines:
        if "Mark King / The Next Revolution" in line and "mark king" not in op_log_text.lower():
            findings.append((
                "coverage_incomplete",
                "ACTIONED suppression not reflected in operational log — Mark King",
                ["ACTIONED contains a Mark King resolution line, but the operational log does not clearly document the same resolution path."],
            ))
            break

    grouped_order = [
        "destination changed but log missing",
        "log says queued but destination now confirmed",
        "coverage_incomplete",
        "blocked",
        "logged and aligned",
    ]
    grouped = {k: [] for k in grouped_order}
    for status, title, bullets in findings:
        grouped.setdefault(status, []).append((title, bullets))

    nonempty = False
    for status in grouped_order:
        items = grouped.get(status) or []
        if not items:
            continue
        nonempty = True
        lines.append(f"## {status}")
        for title, bullets in items:
            lines.append(f"### {title}")
            lines.extend(f"- {bullet}" for bullet in bullets)
            lines.append("")

    if not nonempty:
        lines.append("## Result")
        lines.append("No material proof-layer reconciliation findings.")

    return "\n".join(lines).rstrip() + "\n"


def _extract_email_address(text: str) -> str | None:
    m = re.search(r'([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})', text, re.I)
    return m.group(1).lower() if m else None


def _append_unique_line(path: Path, value: str) -> bool:
    existing = set()
    if path.exists():
        existing = {line.strip() for line in path.read_text(errors='ignore').splitlines() if line.strip()}
    if value in existing:
        return False
    with path.open('a', encoding='utf-8') as f:
        f.write(value + '\n')
    return True


def readable_truth_audit() -> str:
    now = now_utc()
    lines = [
        '# Readable Truth Audit',
        f'_Generated: {now.strftime("%Y-%m-%d %H:%M UTC")}_',
        '',
        '## Scope',
        'Identify consequential mirror/feed items where current readable truth is withheld or weaker than the strength of claim a recurring job might want to make.',
        '',
    ]
    findings: list[tuple[str, str, list[str]]] = []

    watched = [
        ('gmail_external', GMAIL_EXTERNAL_PATH),
        ('microsoft_external', MICROSOFT_EXTERNAL_PATH),
        ('gmail_inbox', GMAIL_INBOX_PATH),
        ('microsoft_inbox', MICROSOFT_INBOX_PATH),
    ]
    high_signal_markers = [
        'lyonsdavidson.co.uk', 'croydemedical.co.uk', 'marketsrecon.com', 'thenextrevolution.co.uk',
        'job application', 'invoice', 'legal', 'claim', 'payment', 'project draw down', 'accepted:',
    ]
    weak_markers = ['[body not shown', 'body content is withheld']
    weak_hits = []
    for source_name, path in watched:
        text = _read_text(path)
        for block in split_message_blocks(text):
            block_text = '\n'.join(block) if isinstance(block, list) else str(block)
            b = block_text.lower()
            if not any(marker in b for marker in weak_markers):
                continue
            if not any(marker in b for marker in high_signal_markers):
                continue
            subj = next((ln.strip('* ') for ln in block if isinstance(block, list) and ln.startswith('**') and ln.endswith('**')), '(no subject)') if isinstance(block, list) else '(no subject)'
            weak_hits.append((source_name, subj[:160]))

    if weak_hits:
        findings.append((
            'coverage_incomplete',
            'Consequential mirror items with withheld body truth',
            [f'{src}: {subj}' for src, subj in weak_hits[:20]],
        ))
    else:
        findings.append((
            'logged and aligned',
            'Consequential mirror/body truth gaps',
            ['No high-signal withheld-body mirror items were detected in the current pass.'],
        ))

    grouped_order = ['destination changed but log missing', 'log says queued but destination now confirmed', 'coverage_incomplete', 'blocked', 'logged and aligned']
    grouped = {k: [] for k in grouped_order}
    for status, title, bullets in findings:
        grouped.setdefault(status, []).append((title, bullets))
    for status in grouped_order:
        items = grouped.get(status) or []
        if not items:
            continue
        lines.append(f'## {status}')
        for title, bullets in items:
            lines.append(f'### {title}')
            lines.extend(f'- {bullet}' for bullet in bullets)
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def bounce_unsub_audit() -> str:
    now = now_utc()
    lines = [
        '# Bounce and Unsubscribe Audit',
        f'_Generated: {now.strftime("%Y-%m-%d %H:%M UTC")}_',
        '',
        '## Scope',
        'Detect bounce/unsubscribe signals from external inbox mirrors and reconcile them into pending prospector queues.',
        '',
    ]
    findings: list[tuple[str, str, list[str]]] = []
    bounce_added = []
    unsub_added = []
    for source_name, path in [('gmail_external', GMAIL_EXTERNAL_PATH), ('microsoft_external', MICROSOFT_EXTERNAL_PATH)]:
        text = _read_text(path)
        for block in split_message_blocks(text):
            block_text = '\n'.join(block) if isinstance(block, list) else str(block)
            b = block_text.lower()
            email = _extract_email_address(block_text)
            if not email:
                continue
            if any(x in b for x in ['undeliverable', 'delivery status notification', 'mail delivery failed', 'returned mail', 'postmaster@', 'mailer-daemon@']):
                if _append_unique_line(PENDING_BOUNCES_PATH, email):
                    bounce_added.append((email, source_name))
            if any(x in b for x in ['unsubscribe', 'remove me', 'opt out', 'opt-out', 'do not contact', 'don\'t contact me']):
                if _append_unique_line(PENDING_UNSUBS_PATH, email):
                    unsub_added.append((email, source_name))
    if bounce_added:
        findings.append(('logged and aligned', 'New bounce signals added', [f'{email} from {src}' for email, src in bounce_added]))
    if unsub_added:
        findings.append(('logged and aligned', 'New unsubscribe signals added', [f'{email} from {src}' for email, src in unsub_added]))
    if not bounce_added and not unsub_added:
        findings.append(('logged and aligned', 'No new bounce/unsubscribe additions', ['No new external inbox signals required queue updates in this run.']))

    grouped_order = ['destination changed but log missing', 'log says queued but destination now confirmed', 'coverage_incomplete', 'blocked', 'logged and aligned']
    grouped = {k: [] for k in grouped_order}
    for status, title, bullets in findings:
        grouped.setdefault(status, []).append((title, bullets))
    for status in grouped_order:
        items = grouped.get(status) or []
        if not items:
            continue
        lines.append(f'## {status}')
        for title, bullets in items:
            lines.append(f'### {title}')
            lines.extend(f'- {bullet}' for bullet in bullets)
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def outbound_completion_audit() -> str:
    now = now_utc()
    lines = [
        "# Outbound Completion Audit",
        f"_Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Scope",
        "Check whether materially meaningful outbound actions (generated, sent, queued) have moved their owning downstream truth layers or remain only noted in logs/queues.",
        "",
    ]

    op_log_text = _read_text(OP_LOG_PATH)
    sharepoint_queue_path = WORKSPACE.parent / "sharepoint-queue.json"
    sharepoint_queue_text = _read_text(sharepoint_queue_path)
    sharepoint_result = _read_text(SHAREPOINT_RESULT_PATH)
    invoice_tracker_json = _read_text(WORKSPACE / "INVOICE_TRACKER.json")
    crm_text = _read_text(CRM_PATH)
    findings: list[tuple[str, str, list[str]]] = []

    try:
        queued_ops = json.loads(sharepoint_queue_text) if sharepoint_queue_text.strip() else []
    except Exception:
        queued_ops = []

    if "sp-mr-622a" in sharepoint_queue_text and "sp-mr-622b" in sharepoint_queue_text:
        mr_ops = [op for op in queued_ops if op.get("id") in {"sp-mr-622a", "sp-mr-622b"}]
        oldest_requested = None
        for op in mr_ops:
            requested = parse_iso(op.get("requested_at"))
            if requested and (oldest_requested is None or requested < oldest_requested):
                oldest_requested = requested
        age_note = None
        if oldest_requested:
            age = now - oldest_requested
            age_note = f"Oldest queued write age: {int(age.total_seconds() // 60)} minutes."

        if "Project Suspended Due to Client Cashflow" in sharepoint_result or "Markets Recon - Current" in sharepoint_result:
            findings.append((
                "log says queued but destination now confirmed",
                "Markets Recon SharePoint queue progression",
                [
                    "Markets Recon writes are still present in the queue, but SharePoint results now appear to show the same write path confirmed.",
                    *( [age_note] if age_note else [] ),
                ],
            ))
        elif oldest_requested and (now - oldest_requested) > timedelta(hours=1):
            findings.append((
                "blocked",
                "Markets Recon SharePoint queue stalled",
                [
                    "Markets Recon writes remain queued and unconfirmed in SharePoint result state beyond the acceptable short-lived queue window.",
                    *( [age_note] if age_note else [] ),
                    "This needs queue-processor/path verification rather than being treated as ordinary short-lived coverage lag.",
                ],
            ))
        else:
            findings.append((
                "coverage_incomplete",
                "Markets Recon SharePoint queue progression",
                [
                    "Markets Recon writes remain queued; outbound completion into SharePoint has not yet been confirmed from result state.",
                    *( [age_note] if age_note else [] ),
                ],
            ))

    if "INV-076" in invoice_tracker_json and "generated and stored" in op_log_text.lower():
        if "2026-06-18%20-%20Invoice%20-%20INV-076.pdf" in invoice_tracker_json:
            findings.append((
                "logged and aligned",
                "INV-076 invoice generation completion",
                ["Invoice generation/store event is reflected in tracker destination truth via the stored invoice link."],
            ))
        else:
            findings.append((
                "destination changed but log missing",
                "INV-076 invoice generation completion",
                ["Operational log says INV-076 was generated/stored, but the tracker destination truth still lacks the stored invoice link."],
            ))

    if "Markets Recon | Kyle Harris" in crm_text and "suspended the planned Stackstone build" in crm_text:
        findings.append((
            "logged and aligned",
            "Markets Recon CRM local completion",
            ["Markets Recon opportunity summary reflects the client-side pause and the next-step reassessment path."],
        ))

    grouped_order = [
        "destination changed but log missing",
        "log says queued but destination now confirmed",
        "coverage_incomplete",
        "blocked",
        "logged and aligned",
    ]
    grouped = {k: [] for k in grouped_order}
    for status, title, bullets in findings:
        grouped.setdefault(status, []).append((title, bullets))

    nonempty = False
    for status in grouped_order:
        items = grouped.get(status) or []
        if not items:
            continue
        nonempty = True
        lines.append(f"## {status}")
        for title, bullets in items:
            lines.append(f"### {title}")
            lines.extend(f"- {bullet}" for bullet in bullets)
            lines.append("")

    if not nonempty:
        lines.append("## Result")
        lines.append("No material outbound completion findings.")

    return "\n".join(lines).rstrip() + "\n"


def operational_activity_log_reconciliation() -> str:
    reconcile_expense_monitor_state()
    lines = [
        "# Operational Activity Log Reconciliation",
        f"_Generated: {now_utc().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Scope",
        "Recent CRM / SharePoint / invoice / expense proof layers vs the review log.",
        "",
    ]

    findings: list[tuple[str, str, list[str]]] = []

    sharepoint_text = _read_text(SHAREPOINT_RESULT_PATH)
    invoice_text = _read_text(INVOICE_TRACKER_PATH)
    health_text = _read_text(SYSTEM_HEALTH_PATH)
    state = load_state()
    whatsapp_text = _read_text(WHATSAPP_RECENT_PATH)

    if "Invoice Sent for July Block" in sharepoint_text and not _log_has("Invoice Sent for July Block"):
        findings.append((
            "destination changed but log missing",
            "Croyde invoice-sent SharePoint communication update",
            [
                "SharePoint result confirms the dated account communication update exists.",
                "Operational log did not yet contain an entry explicitly naming that communication artifact.",
            ],
        ))
    else:
        findings.append((
            "logged and aligned",
            "Croyde invoice-sent SharePoint communication update",
            [
                "SharePoint result confirms the account communication update.",
                "Operational log contains the matching Croyde invoice-sent communication entry.",
            ],
        ))

    if "INV-076" in invoice_text and "| INV-076 | Croyde Medical | Draft |" in invoice_text:
        findings.append((
            "coverage incomplete",
            "INV-076 tracker mirror vs live generation state",
            [
                "Operational log records INV-076 as generated/stored and tracker-updated.",
                "Local INVOICE_TRACKER.md mirror still shows Draft, so the mirror has not caught up and full alignment cannot be proved from the mirror alone.",
            ],
        ))
    elif _log_has("INV-076 generated and stored"):
        findings.append((
            "logged and aligned",
            "INV-076 generation state",
            ["Operational log contains the generation/store event and the tracker mirror no longer contradicts it."],
        ))

    if _log_has("Markets Recon handover to Alex") and "Alex Handover and Data Folder Sent" not in sharepoint_text:
        findings.append((
            "logged and aligned",
            "Markets Recon handover queued state",
            [
                "Operational log says the SharePoint write is queued.",
                "SharePoint results do not yet show confirmation, so the queued state remains the correct review-layer state.",
            ],
        ))
    elif "Alex Handover and Data Folder Sent" in sharepoint_text:
        findings.append((
            "log says queued but destination now confirmed",
            "Markets Recon handover queued state",
            [
                "SharePoint results now show confirmation for the Markets Recon write path.",
                "Operational log still needs advancing from queued to confirmed.",
            ],
        ))

    if "Expense watcher: timer is not enabled" in health_text and _log_has("Expense watcher: timer is not enabled"):
        findings.append((
            "logged and aligned",
            "Expense coverage confidence",
            [
                "System health still shows the expense watcher disabled.",
                "Operational log already records this as coverage incomplete rather than pretending all-clear.",
            ],
        ))
    elif "Expense watcher: timer is not enabled" in health_text:
        findings.append((
            "destination changed but log missing",
            "Expense coverage confidence",
            [
                "System health shows the expense watcher disabled.",
                "Operational log is missing the corresponding coverage-incomplete entry.",
            ],
        ))

    if "Failed to resolve 'login.microsoftonline.com'" in health_text and _log_has("inbox-driven all-clear claims are not trustworthy"):
        findings.append((
            "logged and aligned",
            "Inbox/feed coverage confidence",
            [
                "System health still shows stale/degraded inbox feeds.",
                "Operational log already records inbox coverage as incomplete.",
            ],
        ))

    for item in _recent_whatsapp_expense_items(state):
        canonical = _finance_expense_by_source_ref(str(item.get("id") or ""))
        entity = item.get("entity") or "unknown thread"
        if canonical is None:
            findings.append((
                "coverage incomplete",
                f"WhatsApp expense destination — {entity}",
                [
                    f"No canonical SQLite expense record was found for monitored source `{item.get('id')}`.",
                    "The legacy Markdown archive is deliberately not consulted for closure or status.",
                ],
            ))
        elif canonical["status"] in {"ledger_written", "not_business", "duplicate"}:
            findings.append((
                "logged and aligned",
                f"WhatsApp expense destination — {entity}",
                [
                    f"Canonical SQLite status is `{canonical['status']}` for `{item.get('id')}`.",
                    f"Evidence/ledger reference: `{canonical.get('finance_ledger_ref') or canonical.get('evidence_ref') or 'retained source evidence'}`.",
                ],
            ))
        else:
            findings.append((
                "blocked" if canonical["status"] == "blocked" else "coverage incomplete",
                f"WhatsApp expense destination — {entity}",
                [
                    f"Canonical SQLite status is `{canonical['status']}` for `{item.get('id')}`.",
                    f"Evidence state: `{canonical.get('evidence_state') or 'unverified'}`; settlement state: `{canonical.get('settlement_state') or 'unverified'}`.",
                ],
            ))

    grouped_order = [
        "destination changed but log missing",
        "log says queued but destination now confirmed",
        "coverage incomplete",
        "blocked",
        "logged and aligned",
    ]
    grouped = {k: [] for k in grouped_order}
    for status, title, bullets in findings:
        grouped.setdefault(status, []).append((title, bullets))

    nonempty = False
    for status in grouped_order:
        items = grouped.get(status) or []
        if not items:
            continue
        nonempty = True
        lines.append(f"## {status}")
        for title, bullets in items:
            lines.append(f"### {title}")
            lines.extend(f"- {bullet}" for bullet in bullets)
            lines.append("")

    if not nonempty:
        lines.append("## Result")
        lines.append("No material operational-log reconciliation findings.")

    return "\n".join(lines).rstrip() + "\n"



MEETING_COPILOT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} - (Meeting Summary|Transcript|Recording) - .+\.(md|vtt|mp4)$")
DATED_ENTITY_ARTIFACT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:-\d{2})? - .+\.(md|docx|pdf|vtt|txt)$", re.IGNORECASE)


def classify_sharepoint_path(sp_path: str) -> dict:
    parts = [part for part in sp_path.split('/') if part]
    filename = parts[-1] if parts else sp_path
    result = {
        "file_class": "ignored",
        "entity_kind": None,
        "entity_name": None,
        "reason": "outside monitored SharePoint entity/meeting patterns",
    }
    if len(parts) >= 3 and parts[0] in {"Accounts", "Opportunities", "Partnerships"}:
        entity_kind = {"Accounts": "account", "Opportunities": "opportunity", "Partnerships": "partnership"}[parts[0]]
        entity_name = parts[1]
        result.update({"entity_kind": entity_kind, "entity_name": entity_name})
        if filename.endswith(" - Current.md"):
            result.update({"file_class": "entity_current", "reason": "entity Current.md truth file"})
        elif MEETING_COPILOT_RE.match(filename):
            result.update({"file_class": "meeting_copilot", "reason": "meeting-copilot pattern inside canonical entity folder"})
        elif DATED_ENTITY_ARTIFACT_RE.match(filename):
            result.update({"file_class": "dated_artifact", "reason": "dated entity artifact"})
        elif filename.lower().endswith((".docx", ".pdf", ".pptx", ".xlsx", ".md")):
            result.update({"file_class": "entity_document", "reason": "entity document/report file"})
        return result
    if parts and parts[0] == "Meeting Agent Outputs" and MEETING_COPILOT_RE.match(filename):
        result.update({"file_class": "meeting_copilot_landing", "reason": "meeting-copilot file in landing folder"})
    return result


def load_sharepoint_manifest() -> dict:
    if not SHAREPOINT_MANIFEST_PATH.exists():
        return {"cached": {}}
    return json.loads(SHAREPOINT_MANIFEST_PATH.read_text())


def load_file_watch_state() -> dict:
    if not SHAREPOINT_FILE_WATCH_STATE_PATH.exists():
        return {"last_run_at": None, "files": {}}
    return json.loads(SHAREPOINT_FILE_WATCH_STATE_PATH.read_text())


def save_file_watch_state(state: dict) -> None:
    SHAREPOINT_FILE_WATCH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHAREPOINT_FILE_WATCH_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def save_entity_watch_state(state: dict) -> None:
    SHAREPOINT_ENTITY_WATCH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHAREPOINT_ENTITY_WATCH_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def candidate_from_manifest_entry(sp_path: str, meta: dict, prior_files: dict) -> SharePointFileCandidate | None:
    cls = classify_sharepoint_path(sp_path)
    if cls["file_class"] == "ignored":
        return None
    modified = meta.get("sp_modified") or meta.get("modified") or meta.get("last_modified")
    size = meta.get("size")
    local_path = meta.get("local_path")
    prior = prior_files.get(sp_path, {})
    prior_modified = prior.get("last_seen_modified")
    prior_size = prior.get("last_seen_size")
    if not prior:
        change_state = "new"
        reason = "not present in previous file-watch state"
    elif modified != prior_modified or size != prior_size:
        change_state = "modified"
        reason = "metadata changed since previous file-watch state"
    else:
        change_state = "unchanged"
        reason = "metadata unchanged since previous file-watch state"
    return SharePointFileCandidate(
        path=sp_path,
        file_class=cls["file_class"],
        entity_kind=cls["entity_kind"],
        entity_name=cls["entity_name"],
        modified=modified,
        size=size,
        local_path=local_path,
        change_state=change_state,
        reason=reason,
    )



def normalise_sp_path(path: str | None) -> str:
    if not path:
        return ""
    return path.strip().strip("`").lstrip("/")


def parse_partnership_rows() -> dict[str, dict]:
    if not PARTNERSHIPS_PATH.exists():
        return {}
    rows: dict[str, dict] = {}
    for line in PARTNERSHIPS_PATH.read_text().splitlines():
        if not line.startswith("|") or line.startswith("|------") or line.startswith("| Name "):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 7:
            continue
        name, related_company, partner_type, last_touch = parts[:4]
        path_idx = next((i for i, value in enumerate(parts) if value.startswith("/Partnerships/")), None)
        if path_idx is None or path_idx < 5:
            continue
        rows[name] = {
            "entity_kind": "partnership",
            "entity_name": name,
            "last_touch": last_touch,
            "next_step": " | ".join(parts[4:path_idx]),
            "sharepoint_path": parts[path_idx],
            "notes": " | ".join(parts[path_idx + 1:]),
        }
    return rows


def crm_entity_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for entity in load_entities():
        kind = "account" if entity.section == "Accounts" else "opportunity"
        row = {
            "entity_kind": kind,
            "entity_name": entity.company,
            "last_touch": entity.last_touch,
            "next_step": entity.next_step,
            "sharepoint_path": entity.sharepoint_path,
            "stage": entity.stage,
        }
        index[f"{kind}:{entity.company}"] = row
        if entity.sharepoint_path:
            canonical_path = normalise_sp_path(entity.sharepoint_path)
            index[f"path:{canonical_path}"] = row
            # Canonical SharePoint folder names are authoritative aliases for
            # display names (e.g. Harken Health -> Accounts/Harken). This
            # deterministic mapping prevents false blocked reconciliations.
            parts = canonical_path.split("/")
            if len(parts) >= 2:
                index[f"{kind}:{parts[1]}"] = row
    for name, row in parse_partnership_rows().items():
        index[f"partnership:{name}"] = row
        if row.get("sharepoint_path"):
            canonical_path = normalise_sp_path(row['sharepoint_path'])
            index[f"path:{canonical_path}"] = row
            parts = canonical_path.split("/")
            if len(parts) >= 2:
                index[f"partnership:{parts[1]}"] = row
    return index


def extract_current_summary_fields(text: str) -> dict:
    fields = {"last_touch": None, "next_step": None, "current_position": None}
    m = re.search(r"^\*\*Last touch:\*\*\s*(.+)$", text, re.MULTILINE)
    if m:
        fields["last_touch"] = m.group(1).strip()
    next_match = re.search(r"^## Recommended next step\s*\n(?P<body>.*?)(?:\n## |\Z)", text, re.MULTILINE | re.DOTALL)
    if next_match:
        body = " ".join(line.strip("- ").strip() for line in next_match.group("body").splitlines() if line.strip())
        fields["next_step"] = body[:900]
    pos_match = re.search(r"^## Current position\s*\n(?P<body>.*?)(?:\n## |\Z)", text, re.MULTILINE | re.DOTALL)
    if pos_match:
        body_lines = [line.strip("- ").strip() for line in pos_match.group("body").splitlines() if line.strip()]
        fields["current_position"] = " ".join(body_lines[:4])[:900]
    return fields



def parse_crm_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value or value in {"—", "-"}:
        return None
    # Treat date-only values as calendar dates, not local-midnight instants, to avoid BST -> previous UTC day drift.
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            return None
    parsed = parse_ddmmyyyy(value)
    if parsed:
        return parsed
    parsed = parse_iso(value)
    if parsed:
        return parsed
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def date_relation(left: str | None, right: str | None) -> str:
    left_dt = parse_crm_date(left)
    right_dt = parse_crm_date(right)
    if left_dt and right_dt:
        if left_dt.date() > right_dt.date():
            return "left_newer"
        if left_dt.date() < right_dt.date():
            return "right_newer"
        return "same_day"
    if left and not right:
        return "left_only"
    if right and not left:
        return "right_only"
    return "unknown"

def current_reconciliation_proposals(changed: list[SharePointFileCandidate], include_unchanged: bool = False, all_candidates: list[SharePointFileCandidate] | None = None) -> list[dict]:
    candidates = all_candidates if include_unchanged and all_candidates is not None else changed
    index = crm_entity_index()
    proposals: list[dict] = []
    for candidate in candidates:
        if candidate.file_class != "entity_current":
            continue
        row = index.get(candidate.entity_key or "") or index.get(f"path:{normalise_sp_path(candidate.path)}")
        local_path = WORKSPACE / (candidate.local_path or f"sharepoint-cache/{candidate.path}")
        if not local_path.exists():
            proposals.append({"entity": candidate.entity_key, "path": candidate.path, "outcome": "coverage_incomplete", "reason": "cached Current.md file missing locally"})
            continue
        fields = extract_current_summary_fields(local_path.read_text(errors="replace"))
        if not row:
            proposals.append({"entity": candidate.entity_key, "path": candidate.path, "outcome": "blocked", "reason": "no matching CRM/partnership row found", "current_last_touch": fields.get("last_touch"), "current_next_step": fields.get("next_step")})
            continue
        relation = date_relation(fields.get("last_touch"), row.get("last_touch"))
        actions: list[str] = []
        outcome = "not_needed"
        if relation in {"left_newer", "left_only"}:
            outcome = "crm_update_proposal"
            actions.append(f"CRM last_touch appears stale: {row.get('last_touch')} -> {fields.get('last_touch')}")
            if fields.get("next_step") and fields["next_step"] != row.get("next_step"):
                actions.append("CRM next_step may need update from newer Current.md recommended next step")
        elif relation in {"right_newer", "right_only"}:
            outcome = "current_header_stale"
            actions.append(f"Current.md header appears older than CRM: {fields.get('last_touch')} < {row.get('last_touch')}")
            if fields.get("next_step") and fields["next_step"] != row.get("next_step"):
                actions.append("Current.md recommended next step may lag CRM summary")
        elif relation == "same_day":
            if fields.get("next_step") and fields["next_step"] != row.get("next_step"):
                outcome = "review_next_step_diff"
                actions.append("Same-day next_step differs between Current.md and CRM; needs review before write")
        else:
            if fields.get("next_step") and fields["next_step"] != row.get("next_step"):
                outcome = "review_next_step_diff"
                actions.append("Could not compare dates; next_step differs and needs review")
        proposals.append({"entity": candidate.entity_key, "path": candidate.path, "outcome": outcome, "actions": actions, "crm_last_touch": row.get("last_touch"), "current_last_touch": fields.get("last_touch"), "crm_next_step": row.get("next_step"), "current_next_step": fields.get("next_step")})
    return proposals


def replace_recommended_next_step(content: str, next_step: str) -> tuple[str, bool]:
    if not next_step:
        return content, False
    pattern = re.compile(r"(^## Recommended next step\s*\n)(?P<body>.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    if not pattern.search(content):
        return content, False
    replacement = f"\\1- {next_step.strip()}\n\n"
    return pattern.sub(replacement, content, count=1), True


def normalise_current_header_content(content: str, row: dict, proposal: dict) -> tuple[str, list[str], list[str]]:
    """Return updated content, applied changes, blockers.

    This intentionally avoids broad document rewrites. It only updates clear top-level fields:
    - an existing `**Last touch:**` line
    - an existing `## Recommended next step` section
    """
    blockers: list[str] = []
    changes: list[str] = []
    updated = content
    last_touch = (row.get("last_touch") or "").strip()
    next_step = (row.get("next_step") or "").strip()
    if last_touch:
        updated2, count = re.subn(r"^\*\*Last touch:\*\*\s*.*$", f"**Last touch:** {last_touch}", updated, count=1, flags=re.MULTILINE)
        if count:
            updated = updated2
            changes.append("last_touch")
        else:
            blockers.append("missing Last touch header line")
    else:
        blockers.append("CRM/partnership row has no last_touch")
    if proposal.get("current_next_step") != next_step and next_step:
        updated2, did_replace = replace_recommended_next_step(updated, next_step)
        if did_replace:
            updated = updated2
            changes.append("recommended_next_step")
        else:
            blockers.append("missing Recommended next step section")
    return updated, changes, blockers



def manifest_freshness_status(manifest: dict, max_age_minutes: int = 45) -> dict:
    synced_at = manifest.get("synced_at")
    parsed = parse_iso(synced_at) if synced_at else None
    if not parsed:
        return {"status": "coverage_incomplete", "message": "manifest synced_at missing or unparsable"}
    age_minutes = (now_utc() - parsed).total_seconds() / 60
    if age_minutes > max_age_minutes:
        return {"status": "stale", "age_minutes": round(age_minutes, 1), "message": f"SharePoint manifest is {age_minutes:.1f} minutes old; coverage after synced_at is incomplete"}
    return {"status": "fresh", "age_minutes": round(age_minutes, 1), "message": "SharePoint manifest fresh enough for watch-mode claims"}


def load_blocked_state() -> dict:
    if not SHAREPOINT_BLOCKED_STATE_PATH.exists():
        return {"items": {}}
    try:
        return json.loads(SHAREPOINT_BLOCKED_STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {"items": {}}


def save_blocked_state(state: dict) -> None:
    SHAREPOINT_BLOCKED_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHAREPOINT_BLOCKED_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def update_blocked_state(current_proposals: list[dict], header_queue_results: list[dict], meeting_items: list[dict], write_state: bool = False) -> list[dict]:
    state = load_blocked_state()
    items = state.setdefault("items", {})
    now = now_utc().isoformat()
    current_blocks: list[tuple[str, str, str]] = []
    for item in current_proposals:
        if item.get("outcome") == "blocked":
            current_blocks.append((f"current:{item.get('path')}", item.get("path") or "", item.get("reason") or "blocked current reconciliation"))
    for result in header_queue_results or []:
        for item in result.get("blocked", []):
            reason = item.get("blocker") or "blocked header normalization"
            if "wait for cache refresh" in reason:
                continue
            current_blocks.append((f"header:{item.get('path')}", item.get("path") or "", reason))
    for item in meeting_items:
        if item.get("outcome") == "blocked":
            current_blocks.append((f"meeting:{item.get('path')}", item.get("path") or "", item.get("action") or "blocked meeting routing"))
    seen_keys = {key for key, _, _ in current_blocks}
    for key, path, reason in current_blocks:
        prior = items.get(key, {})
        count = int(prior.get("count", 0)) + 1
        items[key] = {"path": path, "reason": reason, "count": count, "first_seen_at": prior.get("first_seen_at", now), "last_seen_at": now, "status": "escalate" if count >= 2 else "blocked"}
    for key, prior in list(items.items()):
        if key not in seen_keys and prior.get("status") != "resolved":
            prior["status"] = "resolved"
            prior["resolved_at"] = now
    state["last_run_at"] = now
    if write_state:
        save_blocked_state(state)
    return [dict(value, key=key) for key, value in items.items() if value.get("status") in {"blocked", "escalate"}]


def changed_document_review_items(changed: list[SharePointFileCandidate]) -> list[dict]:
    items = []
    for candidate in changed:
        if candidate.file_class != "entity_document":
            continue
        ext = Path(candidate.path).suffix.lower()
        if ext in {".docx", ".pdf", ".pptx", ".xlsx"}:
            items.append({"path": candidate.path, "entity": candidate.entity_key, "outcome": "needs_extraction_review", "action": "Non-MD entity document changed; semantic CRM impact needs extracted-text review before updating next steps."})
    return items




def load_normalization_history() -> dict:
    if not SHAREPOINT_NORMALIZATION_HISTORY_PATH.exists():
        return {"items": {}}
    try:
        return json.loads(SHAREPOINT_NORMALIZATION_HISTORY_PATH.read_text())
    except json.JSONDecodeError:
        return {"items": {}}


def save_normalization_history(state: dict) -> None:
    SHAREPOINT_NORMALIZATION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHAREPOINT_NORMALIZATION_HISTORY_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def normalization_history_key(path: str, source: str, changes: list[str]) -> str:
    return f"{source}|/{path}|{','.join(sorted(changes))}"


def recently_queued_normalization(path: str, source: str, changes: list[str], hours: int = 24) -> bool:
    state = load_normalization_history()
    item = state.get("items", {}).get(normalization_history_key(path, source, changes))
    if not item:
        return False
    queued_at = parse_iso(item.get("queued_at"))
    if not queued_at:
        return True
    return (now_utc() - queued_at).total_seconds() < hours * 3600


def record_normalization_queued(path: str, source: str, changes: list[str], queue_id: str) -> None:
    state = load_normalization_history()
    items = state.setdefault("items", {})
    key = normalization_history_key(path, source, changes)
    items[key] = {"path": f"/{path}", "source": source, "changes": sorted(changes), "queue_id": queue_id, "queued_at": now_utc().isoformat()}
    state["last_updated_at"] = now_utc().isoformat()
    save_normalization_history(state)

def recently_confirmed_sharepoint_update(path: str) -> bool:
    """Best-effort guard against re-queueing before the local SharePoint cache refreshes.

    The queue processor rewrites SHAREPOINT_RESULT.md with the latest processed batch.
    If a path is present there as updated, do not immediately queue another normalization
    for the same path in the same cache window.
    """
    if not SHAREPOINT_RESULT_PATH.exists():
        return False
    needle = f"✓ Updated: /{path}"
    return needle in SHAREPOINT_RESULT_PATH.read_text(errors="replace")

def queue_contains_equivalent(queue: list[dict], path: str, source: str, changes: list[str]) -> bool:
    wanted = sorted(changes)
    for item in queue:
        if item.get("path") == f"/{path}" and item.get("source") == source and sorted(item.get("changes", [])) == wanted:
            return True
    return False


def add_missing_current_sections(content: str, row: dict) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    changes: list[str] = []
    updated = content
    last_touch = (row.get("last_touch") or "").strip()
    next_step = (row.get("next_step") or "").strip()
    if not re.search(r"^#\s+.+", updated, re.MULTILINE):
        blockers.append("missing H1 title")
    if "**Last touch:**" not in updated:
        if last_touch and not blockers:
            updated = re.sub(r"^(#\s+.+\n)", rf"\1\n**Last touch:** {last_touch}\n", updated, count=1, flags=re.MULTILINE)
            changes.append("add_last_touch")
        else:
            blockers.append("CRM/partnership row has no last_touch")
    if "## Recommended next step" not in updated:
        if next_step:
            if not updated.endswith("\n"):
                updated += "\n"
            updated += f"\n## Recommended next step\n- {next_step}\n"
            changes.append("add_recommended_next_step")
        else:
            blockers.append("CRM/partnership row has no next_step")
    return updated, changes, blockers


def queue_template_normalization_updates(proposals: list[dict], max_items: int = 5) -> list[dict]:
    index = crm_entity_index()
    queued: list[dict] = []
    blockers: list[dict] = []
    queue = existing_sharepoint_queue()
    now = now_utc().isoformat()
    for proposal in proposals:
        if proposal.get("outcome") != "current_header_stale":
            continue
        if len(queued) >= max_items:
            blockers.append({"path": proposal.get("path"), "blocker": f"max_items limit reached ({max_items})"})
            continue
        path = proposal.get("path")
        entity = proposal.get("entity") or ""
        row = index.get(entity) or index.get(f"path:{normalise_sp_path(path)}")
        if not row:
            blockers.append({"path": path, "blocker": "no deterministic CRM/partnership row"})
            continue
        local_path = WORKSPACE / f"sharepoint-cache/{path}"
        if not local_path.exists():
            blockers.append({"path": path, "blocker": "cached Current.md missing locally"})
            continue
        content = local_path.read_text(errors="replace")
        updated, changes, local_blockers = add_missing_current_sections(content, row)
        if local_blockers:
            blockers.append({"path": path, "blocker": "; ".join(local_blockers)})
            continue
        if not changes or updated == content:
            continue
        if recently_confirmed_sharepoint_update(path):
            blockers.append({"path": path, "blocker": "recent SharePoint update already confirmed; wait for cache refresh before re-queueing"})
            continue
        source = "sharepoint-origin-watcher-template-normalization"
        if queue_contains_equivalent(queue, path, source, changes):
            blockers.append({"path": path, "blocker": "equivalent update already queued"})
            continue
        if recently_queued_normalization(path, source, changes):
            blockers.append({"path": path, "blocker": "equivalent normalization queued recently; wait for cache refresh before re-queueing"})
            continue
        queue_id = f"sptmpl-{uuid.uuid4().hex[:8]}"
        entry = {"id": queue_id, "operation": "update", "path": f"/{path}", "content": updated, "requested_at": now, "source": source, "changes": changes}
        queue.append(entry)
        record_normalization_queued(path, source, changes, queue_id)
        queued.append({"path": path, "entity": entity, "changes": changes, "queue_id": entry["id"]})
    if queued:
        write_sharepoint_queue(queue)
    return [{"queued": queued, "blocked": blockers}]

def existing_sharepoint_queue() -> list[dict]:
    if not SHAREPOINT_QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(SHAREPOINT_QUEUE_PATH.read_text())
    except json.JSONDecodeError:
        raise RuntimeError(f"SharePoint queue is not valid JSON: {SHAREPOINT_QUEUE_PATH}")
    if isinstance(data, list):
        return data
    raise RuntimeError(f"SharePoint queue has unexpected shape: {type(data).__name__}")


def write_sharepoint_queue(entries: list[dict]) -> None:
    SHAREPOINT_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHAREPOINT_QUEUE_PATH.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")


def queue_header_normalization_updates(proposals: list[dict], max_items: int = 8) -> list[dict]:
    index = crm_entity_index()
    queued: list[dict] = []
    blockers: list[dict] = []
    queue = existing_sharepoint_queue()
    now = now_utc().isoformat()
    for proposal in proposals:
        if proposal.get("outcome") != "current_header_stale":
            continue
        if len(queued) >= max_items:
            blockers.append({"path": proposal.get("path"), "blocker": f"max_items limit reached ({max_items})"})
            continue
        path = proposal.get("path")
        entity = proposal.get("entity") or ""
        row = index.get(entity) or index.get(f"path:{normalise_sp_path(path)}")
        if not row:
            blockers.append({"path": path, "blocker": "no deterministic CRM/partnership row"})
            continue
        local_path = WORKSPACE / f"sharepoint-cache/{path}"
        if not local_path.exists():
            blockers.append({"path": path, "blocker": "cached Current.md missing locally"})
            continue
        content = local_path.read_text(errors="replace")
        updated, changes, local_blockers = normalise_current_header_content(content, row, proposal)
        if local_blockers:
            blockers.append({"path": path, "blocker": "; ".join(local_blockers)})
            continue
        if not changes or updated == content:
            continue
        entry = {
            "id": f"spnorm-{uuid.uuid4().hex[:8]}",
            "operation": "update",
            "path": f"/{path}",
            "content": updated,
            "requested_at": now,
            "source": "sharepoint-origin-watcher-header-normalization",
            "changes": changes,
        }
        queue.append(entry)
        queued.append({"path": path, "entity": entity, "changes": changes, "queue_id": entry["id"]})
    if queued:
        write_sharepoint_queue(queue)
    return [{"queued": queued, "blocked": blockers}]

def parse_meeting_copilot_filename(sp_path: str) -> dict:
    filename = sp_path.split("/")[-1]
    m = re.match(r"^(?P<date>\d{4}-\d{2}-\d{2}) - (?P<kind>Meeting Summary|Transcript|Recording) - (?P<title>.+)\.(?P<ext>md|vtt|mp4)$", filename)
    if not m:
        return {"matched": False}
    return {"matched": True, **m.groupdict()}


def meeting_copilot_routing_items(changed: list[SharePointFileCandidate]) -> list[dict]:
    items = []
    for candidate in changed:
        if candidate.file_class not in {"meeting_copilot", "meeting_copilot_landing"}:
            continue
        parsed = parse_meeting_copilot_filename(candidate.path)
        if candidate.entity_key:
            outcome = "not_needed"
            action = "Already in canonical entity folder; later phases may reconcile content if changed."
        else:
            outcome = "blocked"
            action = "Landing file needs entity identification before move/reconcile."
        items.append({"path": candidate.path, "entity": candidate.entity_key, "outcome": outcome, "action": action, "parsed": parsed})
    return items

def build_sharepoint_origin_watch(dry_run: bool = True, write_state: bool = False, include_unchanged_current: bool = False, queue_header_normalization: bool = False, queue_template_normalization: bool = False, max_queue_items: int = 8) -> tuple[str, dict, dict]:
    manifest = load_sharepoint_manifest()
    cached = manifest.get("cached", {})
    prior_state = load_file_watch_state()
    prior_files = prior_state.get("files", {})
    run_at = now_utc().isoformat()
    all_candidates: list[SharePointFileCandidate] = []
    changed: list[SharePointFileCandidate] = []
    for sp_path, meta in cached.items():
        candidate = candidate_from_manifest_entry(sp_path, meta, prior_files)
        if not candidate:
            continue
        all_candidates.append(candidate)
        if candidate.change_state in {"new", "modified"}:
            changed.append(candidate)
    entities: dict[str, dict] = {}
    landing_items: list[SharePointFileCandidate] = []
    for candidate in changed:
        if candidate.entity_key:
            entry = entities.setdefault(candidate.entity_key, {
                "entity_kind": candidate.entity_kind,
                "entity_name": candidate.entity_name,
                "dirty": True,
                "dirty_reasons": [],
                "changed_files": [],
                "last_reconciliation_outcome": "pending_dry_run",
            })
            entry["dirty_reasons"].append(f"{candidate.change_state}:{candidate.file_class}:{candidate.path}")
            entry["changed_files"].append(candidate.path)
        elif candidate.file_class == "meeting_copilot_landing":
            landing_items.append(candidate)
    new_file_state = {"last_run_at": run_at, "source_synced_at": manifest.get("synced_at"), "files": {}}
    for candidate in all_candidates:
        prior = prior_files.get(candidate.path, {})
        new_file_state["files"][candidate.path] = {
            "path": candidate.path,
            "class": candidate.file_class,
            "entity_kind": candidate.entity_kind,
            "entity_name": candidate.entity_name,
            "last_seen_modified": candidate.modified,
            "last_seen_size": candidate.size,
            "local_path": candidate.local_path,
            "last_processed_modified": prior.get("last_processed_modified"),
            "last_processed_outcome": prior.get("last_processed_outcome", "pending_dry_run" if candidate.change_state in {"new", "modified"} else "not_needed"),
            "last_blocker": prior.get("last_blocker"),
        }
    proposals = current_reconciliation_proposals(changed, include_unchanged=include_unchanged_current, all_candidates=all_candidates)
    meeting_items = meeting_copilot_routing_items(changed)
    header_queue_results = queue_header_normalization_updates(proposals, max_items=max_queue_items) if queue_header_normalization else []
    template_queue_results = queue_template_normalization_updates(proposals, max_items=max_queue_items) if queue_template_normalization else []
    document_review_items = changed_document_review_items(changed)
    blocked_items = update_blocked_state(proposals, header_queue_results + template_queue_results, meeting_items, write_state=write_state)
    freshness = manifest_freshness_status(manifest)
    entity_state = {
        "last_run_at": run_at,
        "source_synced_at": manifest.get("synced_at"),
        "entities": entities,
        "meeting_copilot_landing_items": [candidate.path for candidate in landing_items],
        "current_reconciliation_proposals": proposals,
        "meeting_copilot_routing_items": meeting_items,
        "header_normalization_queue_results": header_queue_results,
        "template_normalization_queue_results": template_queue_results,
        "document_review_items": document_review_items,
        "blocked_items": blocked_items,
        "manifest_freshness": freshness,
    }
    report = render_sharepoint_origin_report(run_at, manifest, all_candidates, changed, entities, landing_items, dry_run, proposals, meeting_items, header_queue_results, template_queue_results, document_review_items, blocked_items, freshness)
    if write_state:
        save_file_watch_state(new_file_state)
        save_entity_watch_state(entity_state)
        SHAREPOINT_ORIGIN_RECON_PATH.write_text(report)
    return report, new_file_state, entity_state


def render_sharepoint_origin_report(run_at: str, manifest: dict, all_candidates: list[SharePointFileCandidate], changed: list[SharePointFileCandidate], entities: dict[str, dict], landing_items: list[SharePointFileCandidate], dry_run: bool, current_proposals: list[dict] | None = None, meeting_items: list[dict] | None = None, header_queue_results: list[dict] | None = None, template_queue_results: list[dict] | None = None, document_review_items: list[dict] | None = None, blocked_items: list[dict] | None = None, freshness: dict | None = None) -> str:
    lines = [
        "# SharePoint Origin Reconciliation Report",
        "",
        f"Run: {run_at}",
        f"Mode: {'dry-run' if dry_run else 'watch'}",
        f"Manifest synced_at: {manifest.get('synced_at', 'unknown')}",
        "",
        "## Summary",
        f"- Monitored SharePoint files in manifest: {len(all_candidates)}",
        f"- Changed/new monitored files since prior state: {len(changed)}",
        f"- Dirty entities: {len(entities)}",
        f"- Meeting Copilot landing items needing routing: {len(landing_items)}",
        f"- Manifest freshness: {(freshness or {}).get('status', 'unknown')} — {(freshness or {}).get('message', 'not checked')}",
        "",
    ]
    if changed:
        lines += ["## Changed/new monitored files", "", "| state | class | entity | path |", "|---|---|---|---|"]
        for candidate in sorted(changed, key=lambda c: (c.entity_key or '', c.path))[:200]:
            entity = candidate.entity_key or "unassigned"
            lines.append(f"| {candidate.change_state} | {candidate.file_class} | {entity} | `{candidate.path}` |")
        if len(changed) > 200:
            lines.append(f"| ... | ... | ... | {len(changed) - 200} additional changed files omitted from compact report |")
        lines.append("")
    else:
        lines += ["## Changed/new monitored files", "", "None detected since prior state.", ""]
    if entities:
        lines += ["## Dirty entities", "", "| entity | changed files | next action |", "|---|---:|---|"]
        for entity_key, entry in sorted(entities.items()):
            lines.append(f"| {entity_key} | {len(entry['changed_files'])} | Dry-run only: Phase 2 reconciliation must inspect changed files before CRM/Current writes |")
        lines.append("")
    if landing_items:
        lines += ["## Meeting Copilot landing items", "", "| path | action |", "|---|---|"]
        for candidate in landing_items:
            lines.append(f"| `{candidate.path}` | Needs entity identification and canonical filing decision |")
        lines.append("")
    current_proposals = current_proposals or []
    meeting_items = meeting_items or []
    if current_proposals:
        lines += ["## Current.md reconciliation dry-run", "", "| outcome | entity | path | action |", "|---|---|---|---|"]
        for item in current_proposals[:120]:
            action = "; ".join(item.get("actions") or [item.get("reason", "No CRM/Current change proposed")])
            lines.append(f"| {item.get('outcome')} | {item.get('entity') or ''} | `{item.get('path')}` | {action} |")
        lines.append("")
    if meeting_items:
        lines += ["## Meeting Copilot routing dry-run", "", "| outcome | entity | path | action |", "|---|---|---|---|"]
        for item in meeting_items[:120]:
            lines.append(f"| {item.get('outcome')} | {item.get('entity') or ''} | `{item.get('path')}` | {item.get('action')} |")
        lines.append("")
    header_queue_results = header_queue_results or []
    if header_queue_results:
        result = header_queue_results[0]
        lines += ["## Header normalization queue result", "", "| state | path | detail |", "|---|---|---|"]
        for item in result.get("queued", []):
            lines.append(f"| queued | `{item.get('path')}` | {item.get('queue_id')} / {', '.join(item.get('changes', []))} |")
        for item in result.get("blocked", [])[:80]:
            lines.append(f"| blocked | `{item.get('path')}` | {item.get('blocker')} |")
        lines.append("")
    template_queue_results = template_queue_results or []
    if template_queue_results:
        result = template_queue_results[0]
        lines += ["## Template normalization queue result", "", "| state | path | detail |", "|---|---|---|"]
        for item in result.get("queued", []):
            lines.append(f"| queued | `{item.get('path')}` | {item.get('queue_id')} / {', '.join(item.get('changes', []))} |")
        for item in result.get("blocked", [])[:80]:
            lines.append(f"| blocked | `{item.get('path')}` | {item.get('blocker')} |")
        lines.append("")
    document_review_items = document_review_items or []
    if document_review_items:
        lines += ["## Changed non-MD documents needing semantic review", "", "| outcome | entity | path | action |", "|---|---|---|---|"]
        for item in document_review_items[:80]:
            lines.append(f"| {item.get('outcome')} | {item.get('entity') or ''} | `{item.get('path')}` | {item.get('action')} |")
        lines.append("")
    blocked_items = blocked_items or []
    if blocked_items:
        lines += ["## Blocked item review", "", "| status | count | path | reason |", "|---|---:|---|---|"]
        for item in sorted(blocked_items, key=lambda x: (x.get('status') != 'escalate', x.get('path','')))[:80]:
            lines.append(f"| {item.get('status')} | {item.get('count')} | `{item.get('path')}` | {item.get('reason')} |")
        lines.append("")
    lines += [
        "## Status",
        "This watcher currently detects metadata changes, writes state, groups dirty entities, and produces dry-run Current.md / Meeting Copilot reconciliation proposals. It does not yet write CRM, Current.md, or SharePoint automatically.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inbound monitoring runtime helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    r1 = sub.add_parser("crm-sharepoint-report", help="Generate CRM/SharePoint drift report")
    r1.add_argument("--write", action="store_true", help="Write report to memory/crm-sharepoint-reconciliation.md")

    r2 = sub.add_parser("blocked-report", help="Generate blocked monitored-items report")
    r2.add_argument("--write", action="store_true", help="Write report to memory/blocked-monitored-items.md")

    r3 = sub.add_parser("operational-log-report", help="Generate operational activity log reconciliation report")
    r3.add_argument("--write", action="store_true", help="Write report to memory/operational-activity-log-reconciliation.md")

    r4 = sub.add_parser("proof-layer-report", help="Generate cross-layer proof reconciliation report")
    r4.add_argument("--write", action="store_true", help="Write report to memory/proof-layer-reconciliation.md")

    r4b = sub.add_parser("outbound-completion-report", help="Generate outbound completion audit report")
    r4b.add_argument("--write", action="store_true", help="Write report to memory/outbound-completion-audit.md")

    r4c = sub.add_parser("bounce-unsub-report", help="Generate bounce/unsubscribe audit report")
    r4c.add_argument("--write", action="store_true", help="Write report to memory/bounce-unsub-audit.md")

    r4d = sub.add_parser("readable-truth-report", help="Generate readable-truth audit report")
    r4d.add_argument("--write", action="store_true", help="Write report to memory/readable-truth-audit.md")

    r5 = sub.add_parser("website-activity-report", help="Generate website activity continuity report and update surface state")
    r5.add_argument("--write", action="store_true", help="Write report to memory/website-activity-continuity.md")

    r6 = sub.add_parser("gmail-continuity-report", help="Generate Gmail continuity report and update surface state")
    r6.add_argument("--write", action="store_true", help="Write report to memory/gmail-continuity.md")

    r6b = sub.add_parser("assistant-inbox-continuity-report", help="Generate Assistant inbox continuity report and update surface state")
    r6b.add_argument("--write", action="store_true", help="Write report to memory/assistant-inbox-continuity.md")

    r6c = sub.add_parser("assistant-external-continuity-report", help="Generate Assistant external continuity report and update surface state")
    r6c.add_argument("--write", action="store_true", help="Write report to memory/assistant-external-continuity.md")

    r6d = sub.add_parser("gmail-external-continuity-report", help="Generate Gmail external continuity report and update surface state")
    r6d.add_argument("--write", action="store_true", help="Write report to memory/gmail-external-continuity.md")

    r7 = sub.add_parser("microsoft-continuity-report", help="Generate Microsoft inbox continuity report and update surface state")
    r7.add_argument("--write", action="store_true", help="Write report to memory/microsoft-inbox-continuity.md")

    r7b = sub.add_parser("microsoft-external-continuity-report", help="Generate Microsoft external continuity report and update surface state")
    r7b.add_argument("--write", action="store_true", help="Write report to memory/microsoft-external-continuity.md")

    r8 = sub.add_parser("whatsapp-continuity-report", help="Generate WhatsApp continuity report and update surface state")
    r8.add_argument("--write", action="store_true", help="Write report to memory/whatsapp-continuity.md")

    r8a = sub.add_parser("teams-continuity-report", help="Generate Teams continuity report and update surface state")
    r8a.add_argument("--write", action="store_true", help="Write report to memory/teams-continuity.md")

    r8aa = sub.add_parser("teams-routing-report", help="Classify Teams JSON feed items into the monitored-item routing model")
    r8aa.add_argument("--write", action="store_true", help="Write report to memory/teams-routing.md")
    r8aa.add_argument("--write-state", action="store_true", help="Upsert consequential Teams items into memory/monitored-items-state.json")

    r8ab = sub.add_parser("mirror-routing-report", help="Build canonical mirror events and classify them through the central router")
    r8ab.add_argument("--surface", action="append", help="Surface key to include; repeatable. Defaults to all first-class + outbound-context surfaces")
    r8ab.add_argument("--write", action="store_true", help="Write report to memory/mirror-routing.md")
    r8ab.add_argument("--write-json", action="store_true", help="Write canonical events to memory/mirror-events.json")
    r8ab.add_argument("--write-state", action="store_true", help="Upsert consequential classified items into memory/monitored-items-state.json")
    r8ab.add_argument("--only-new", action="store_true", help="Route only events not already seen in memory/mirror-router-state.json")
    r8ab.add_argument("--mark-seen", action="store_true", help="Mark all currently visible events as seen without requiring them to be management-worthy")

    r8ac = sub.add_parser("migrate-identityless-router-state", help="Expose legacy identityless router seen keys as durable coverage-incomplete ledger entries")
    r8ac.add_argument("--write", action="store_true", help="Write the idempotent migration to router and monitored-item state")

    r8b = sub.add_parser("assistant-sent-continuity-report", help="Generate Assistant sent continuity report and update surface state")
    r8b.add_argument("--write", action="store_true", help="Write report to memory/assistant-sent-continuity.md")

    r8bg = sub.add_parser("gmail-sent-continuity-report", help="Generate Gmail sent continuity report and update surface state")
    r8bg.add_argument("--write", action="store_true", help="Write report to memory/gmail-sent-continuity.md")

    r8c = sub.add_parser("microsoft-sent-continuity-report", help="Generate Microsoft sent continuity report and update surface state")
    r8c.add_argument("--write", action="store_true", help="Write report to memory/microsoft-sent-continuity.md")

    r9 = sub.add_parser("surface-audit-report", help="Generate coverage audit across first-class and live monitored surfaces")
    r9.add_argument("--write", action="store_true", help="Write report to memory/monitoring-surface-audit.md")

    r10 = sub.add_parser("sharepoint-origin-report", help="Detect SharePoint-origin changes and write dry-run watcher state/report")
    r10.add_argument("--write", action="store_true", help="Write report and state to memory/sharepoint-*-watch-state.json and memory/sharepoint-origin-reconciliation.md")
    r10.add_argument("--include-unchanged-current", action="store_true", help="Also run Current.md reconciliation dry-run across unchanged current files")
    r10.add_argument("--queue-header-normalization", action="store_true", help="Queue safe Current.md header-normalization updates for deterministic current_header_stale proposals")
    r10.add_argument("--queue-template-normalization", action="store_true", help="Queue safe template additions for Current.md files missing Last touch / Recommended next step sections")
    r10.add_argument("--max-queue-items", type=int, default=8, help="Maximum header-normalization SharePoint updates to queue in one run")

    u = sub.add_parser("upsert-item", help="Create or update a monitored item in state")
    u.add_argument("--id", required=True)
    u.add_argument("--surface")
    u.add_argument("--entity")
    u.add_argument("--thread-key")
    u.add_argument("--source-timestamp")
    u.add_argument("--seen-at")
    u.add_argument("--flags", help="Comma-separated flags")
    u.add_argument("--mode")
    u.add_argument("--closure-state")
    u.add_argument("--blocker")
    u.add_argument("--evidence-ref")
    u.add_argument("--resolved-at")

    s = sub.add_parser("upsert-surface", help="Create or update monitoring surface continuity state")
    s.add_argument("--surface", required=True)
    s.add_argument("--source-file")
    s.add_argument("--last-check-attempt")
    s.add_argument("--last-successful-check")
    s.add_argument("--last-successful-visible-update")
    s.add_argument("--last-result-shape")
    s.add_argument("--coverage-state")
    s.add_argument("--notes")

    args = parser.parse_args()
    if args.command == "crm-sharepoint-report":
        report = crm_sharepoint_reconciliation()
        if args.write:
            CRM_RECON_PATH.write_text(report)
        print(report, end="")
    elif args.command == "proof-layer-report":
        report = proof_layer_reconciliation()
        if args.write:
            PROOF_LAYER_RECON_PATH.write_text(report)
        print(report, end="")
    elif args.command == "outbound-completion-report":
        report = outbound_completion_audit()
        if args.write:
            OUTBOUND_COMPLETION_PATH.write_text(report)
        print(report, end="")
    elif args.command == "bounce-unsub-report":
        report = bounce_unsub_audit()
        if args.write:
            BOUNCE_UNSUB_PATH.write_text(report)
        print(report, end="")
    elif args.command == "readable-truth-report":
        report = readable_truth_audit()
        if args.write:
            READABLE_TRUTH_PATH.write_text(report)
        print(report, end="")
    elif args.command == "blocked-report":
        report = blocked_items_report()
        if args.write:
            BLOCKED_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "operational-log-report":
        report = operational_activity_log_reconciliation()
        if args.write:
            OP_LOG_RECON_PATH.write_text(report)
        print(report, end="")
    elif args.command == "website-activity-report":
        report = website_activity_continuity_report()
        if args.write:
            SURFACE_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "gmail-continuity-report":
        report = gmail_continuity_report()
        if args.write:
            GMAIL_SURFACE_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "assistant-inbox-continuity-report":
        report = assistant_inbox_continuity_report()
        if args.write:
            ASSISTANT_INBOX_SURFACE_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "assistant-external-continuity-report":
        report = assistant_external_continuity_report()
        if args.write:
            ASSISTANT_EXTERNAL_SURFACE_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "gmail-external-continuity-report":
        report = gmail_external_continuity_report()
        if args.write:
            GMAIL_EXTERNAL_SURFACE_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "microsoft-continuity-report":
        report = microsoft_continuity_report()
        if args.write:
            MICROSOFT_SURFACE_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "microsoft-external-continuity-report":
        report = microsoft_external_continuity_report()
        if args.write:
            MICROSOFT_EXTERNAL_SURFACE_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "whatsapp-continuity-report":
        report = whatsapp_continuity_report()
        if args.write:
            WHATSAPP_SURFACE_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "teams-continuity-report":
        report = teams_continuity_report()
        if args.write:
            (WORKSPACE / "memory/teams-continuity.md").write_text(report)
        print(report, end="")
    elif args.command == "teams-routing-report":
        report = teams_routing_report(write_state=args.write_state)
        if args.write:
            TEAMS_ROUTING_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "mirror-routing-report":
        report = mirror_routing_report(
            surface_keys=args.surface,
            write_json=args.write_json,
            write_state=args.write_state,
            only_new=args.only_new,
            mark_seen=args.mark_seen,
        )
        if args.write:
            MIRROR_ROUTING_REPORT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "migrate-identityless-router-state":
        result = migrate_identityless_router_state(write=args.write)
        print(json.dumps(result, indent=2))
    elif args.command == "assistant-sent-continuity-report":
        report = assistant_sent_continuity_report()
        if args.write:
            (WORKSPACE / "memory/assistant-sent-continuity.md").write_text(report)
        print(report, end="")
    elif args.command == "gmail-sent-continuity-report":
        report = gmail_sent_continuity_report()
        if args.write:
            (WORKSPACE / "memory/gmail-sent-continuity.md").write_text(report)
        print(report, end="")
    elif args.command == "microsoft-sent-continuity-report":
        report = microsoft_sent_continuity_report()
        if args.write:
            (WORKSPACE / "memory/microsoft-sent-continuity.md").write_text(report)
        print(report, end="")
    elif args.command == "surface-audit-report":
        report = monitoring_surface_audit_report()
        if args.write:
            SURFACE_AUDIT_PATH.write_text(report)
        print(report, end="")
    elif args.command == "sharepoint-origin-report":
        report, _, _ = build_sharepoint_origin_watch(dry_run=True, write_state=args.write, include_unchanged_current=args.include_unchanged_current, queue_header_normalization=args.queue_header_normalization, queue_template_normalization=args.queue_template_normalization, max_queue_items=args.max_queue_items)
        print(report, end="")
    elif args.command == "upsert-item":
        print(upsert_item(args))
    elif args.command == "upsert-surface":
        print(upsert_surface(args))
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

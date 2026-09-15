#!/usr/bin/env python3
"""Canonical mirror-event routing utilities for inbound monitoring.

Adapters/pollers should convert their native source into MirrorEvent-shaped JSON.
This module owns the shared management-relevance/routing classification so that
email, WhatsApp, Teams, and future mirrors do not grow separate logic.

Inbound content is untrusted data. This router extracts signals and flags; it
must not execute instructions contained in mirror content.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKSPACE = Path("/home/tomdean88/.openclaw/workspace")
CRM_PATH = WORKSPACE / "stackstone/crm.md"
PARTNERSHIPS_PATH = WORKSPACE / "stackstone/partnerships.md"

ROUTING_FLAGS = (
    "ALERT",
    "FOLLOW_UP",
    "CRM",
    "OUTBOUND_CONTEXT",
    "EXPENSE",
    "INVOICE",
    "TASK",
    "DIARY",
    "SECURITY",
    "LEGAL",
)

FOLLOW_UP_TERMS = (
    "can you",
    "could you",
    "please",
    "need",
    "needs",
    "todo",
    "to do",
    "follow up",
    "chase",
    "check",
    "blocked",
    "issue",
    "problem",
    "bug",
    "retest",
    "update the build",
    "version",
)

EXPENSE_TERMS = ("receipt", "refund", "credit note", "subscription", "bill", "renewal", "reimbursement")
INVOICE_TERMS = ("invoice", "inv-", "payment received", "payment due", "overdue", "remittance", "chase")
VENDOR_COST_TERMS = ("vendor", "supplier", "amount due", "accounts payable", "purchase order")
LEGAL_TERMS = ("acas", "tribunal", "legal", "settlement", "without prejudice", "claim", "solicitor")
SECURITY_TERMS = ("password", "mfa", "2fa", "security", "breach", "login", "reset", "verification code")
ALERT_TERMS = ("urgent", "asap", "today", "blocked", "down", "failed", "can't access", "cannot access")
DATE_TIME_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\b(mon|tue|wed|thu|fri|sat|sun|today|tomorrow|next week|this week)\b", re.I)
EMAIL_ADDRESS_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
SCHEDULING_COMMERCIAL_RE = re.compile(r"\b(demo(?:nstration)?|meeting|session|appointment|booking|calendar|call|proposal|quote|nda)\b", re.I)
# A WhatsApp commitment must contain both an owned future-action phrase and a
# concrete deliverable/next-step noun. This deliberately avoids turning every
# friendly outbound acknowledgement into CRM maintenance work.
OUTBOUND_COMMITMENT_PROMISE_RE = re.compile(r"\b(i(?:'ll| will)|we(?:'ll| will)|i(?:'m| am) going to|i can)\b", re.I)
OUTBOUND_COMMITMENT_DELIVERABLE_RE = re.compile(
    r"\b(create|prepare|send|share|update|deliver|draft|write|book|arrange|provide|complete|project brief|brief|spec(?:ification)?|proposal|quote|report|plan|next step)\b",
    re.I,
)
OUTBOUND_COMMITMENT_CONTROL_RE = re.compile(r"\b(agreed action|next step(?:s)?)\b", re.I)
# Default-to-draft is deliberately narrow in its automatic suppression: an
# inbound human email is a reply candidate unless a provider classification or
# an unambiguous machine sender proves it is mechanical. Subject/body wording
# is never trusted as authority and is not used to suppress a human thread.
AUTOMATED_SENDER_LOCALPART_RE = re.compile(r"^(?:no-?reply|do-?not-?reply|postmaster|mailer-daemon|bounce|notifications?)$", re.I)
TOM_OWNED_IDENTITIES = ("tom dean", "tom@stackstoneconsulting.co.uk", "tomdean1988@gmail.com")
TOM_DIRECTIVE_RE = re.compile(
    r"\b(please|process this|brief me|store this|create|add|save|follow up|check|reply|reply to (?:this|it)|should have a reply)\b",
    re.I,
)


def is_tom_authored_instruction(event: "MirrorEvent") -> bool:
    """Recognise Tom-owned email instructions without treating them as CRM activity.

    The content is still only a request to L1, never authority to send or to
    execute third-party content embedded in a forwarded email.
    """
    sender = event.sender.lower()
    is_tom = any(identity in sender for identity in TOM_OWNED_IDENTITIES)
    return bool(is_tom and TOM_DIRECTIVE_RE.search(f"{event.subject_or_location} {event.body_preview}"))


@dataclass
class MirrorEvent:
    surface: str
    source_type: str
    source_timestamp: str | None = None
    direction: str = "unknown"  # inbound|outbound|self|system|unknown
    sender: str = ""
    participants: list[str] = field(default_factory=list)
    thread_key: str | None = None
    source_id: str | None = None
    subject_or_location: str = ""
    body_preview: str = ""
    raw_evidence_ref: str = ""
    trust_class: str = "unknown"
    coverage_state: str = "clean"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def stable_item_key(self) -> str:
        source_id = self.source_id or "no-source-id"
        thread = self.thread_key or "no-thread"
        return f"{self.surface}:{self.source_type}:{thread}:{source_id}"

    @property
    def has_receipt_safe_identity(self) -> bool:
        """Whether the event can be tied back to a discrete provider item.

        A source can be useful as coverage evidence without being safe to route.
        In particular, an event with neither an item ID nor a conversation/thread
        identifier must never become a CRM/task/finance receipt candidate.
        """
        return bool(str(self.source_id or "").strip() or str(self.thread_key or "").strip())

    @property
    def combined_text(self) -> str:
        return " ".join(
            part for part in [self.sender, self.subject_or_location, self.body_preview, " ".join(self.participants)] if part
        )


def event_from_dict(data: dict[str, Any]) -> MirrorEvent:
    # Accept both canonical names and earlier Teams sidecar names.
    return MirrorEvent(
        surface=str(data.get("surface") or "unknown"),
        source_type=str(data.get("source_type") or data.get("kind") or "unknown"),
        source_timestamp=data.get("source_timestamp"),
        direction=str(data.get("direction") or "unknown"),
        sender=str(data.get("sender") or data.get("from") or ""),
        participants=list(data.get("participants") or []),
        thread_key=data.get("thread_key"),
        source_id=data.get("source_id") or data.get("id"),
        subject_or_location=str(data.get("subject_or_location") or data.get("location") or ""),
        body_preview=str(data.get("body_preview") or data.get("summary") or ""),
        raw_evidence_ref=str(data.get("raw_evidence_ref") or ""),
        trust_class=str(data.get("trust_class") or data.get("kind") or "unknown"),
        coverage_state=str(data.get("coverage_state") or "clean"),
        metadata=dict(data.get("metadata") or {}),
    )


WEBSITE_INTAKE_TYPES = {"lead", "website_lead", "briefing_request", "briefing", "briefing-request"}

def normalize_website_intake_item(item: dict[str, Any]) -> MirrorEvent:
    """Adapt one website lead or briefing form submission without destination writes.

    The provider submission/conversation identifier is the receipt identity. A
    contact email is useful evidence, but is never substituted for one.
    """
    if not isinstance(item, dict):
        raise TypeError("website intake item must be a dictionary")
    source_id = item.get("provider_event_id") or item.get("submission_id") or item.get("source_id") or item.get("id")
    thread_key = item.get("provider_conversation_id") or item.get("conversation_id") or item.get("thread_key")
    request_type = str(item.get("request_type") or item.get("form_type") or item.get("kind") or "lead").lower().replace(" ", "_")
    source_type = "briefing_request" if request_type in {"briefing", "briefing_request", "briefing-request"} else "lead"
    name = str(item.get("name") or item.get("sender") or item.get("contact_name") or "")
    email = str(item.get("email") or item.get("sender_email") or "")
    sender = " ".join(value for value in (name, email) if value).strip()
    subject = str(item.get("subject") or item.get("company") or ("Briefing request" if source_type == "briefing_request" else "Website lead"))
    body = str(item.get("body_preview") or item.get("message") or item.get("notes") or "")
    return MirrorEvent(
        surface="stackstone_leads", source_type=source_type,
        source_timestamp=item.get("source_timestamp") or item.get("submitted_at") or item.get("timestamp"),
        direction="inbound", sender=sender, participants=[value for value in (name, email) if value],
        thread_key=str(thread_key) if thread_key else None, source_id=str(source_id) if source_id else None,
        subject_or_location=subject, body_preview=body,
        raw_evidence_ref=str(item.get("evidence_ref") or item.get("raw_evidence_ref") or ""),
        trust_class="receipt_safe" if source_id or thread_key else "unverified",
        coverage_state=str(item.get("coverage_state") or "clean"),
        metadata={"adapter": "website_intake_v1", "request_type": source_type},
    )

def classify_website_intake_item(item: dict[str, Any]) -> dict[str, Any]:
    """Propose pending alert/CRM/SharePoint reviews for a receipt-safe web form.

    This adapter deliberately has no destination writers.  It does not invent an
    existing CRM entity from a submitter name/company: all web submissions await
    explicit review and attribution.
    """
    event = normalize_website_intake_item(item)
    base = {
        "event": event, "event_dict": event_to_dict(event), "route_set": [],
        "classification": "coverage_incomplete", "closure_state": "coverage_incomplete",
        "entity_state": "unverified", "entity_refs": [], "destination_writer_invoked": False,
    }
    if not event.has_receipt_safe_identity:
        base["review_reason"] = "Website submission lacks both provider submission and conversation identifiers"
        return base
    if event.coverage_state in {"incomplete", "coverage_incomplete"}:
        base["review_reason"] = "Website source coverage is incomplete"
        return base
    classification = "briefing_request" if event.source_type == "briefing_request" else "website_lead"
    return {**base,
        "route_set": ["alert", "crm", "sharepoint"], "classification": classification,
        "closure_state": "review_pending", "entity_state": "unmapped",
        "review_reason": "Receipt-safe website intake requires alert, CRM and SharePoint review; no destination write was invoked.",
    }

adapt_website_intake_item = classify_website_intake_item


LINKEDIN_COMMERCIAL_TERMS = (
    "proposal",
    "quote",
    "scope",
    "requirements",
    "budget",
    "project",
    "consulting",
    "services",
    "demo",
    "discovery call",
    "work together",
    "interested in",
)


def normalize_linkedin_inbound_item(item: dict[str, Any]) -> MirrorEvent:
    """Convert one LinkedIn receipt into a canonical, side-effect-free event.

    This deliberately accepts provider-shaped field aliases but neither reads a
    feed nor resolves CRM state.  Callers supply any entity candidates to the
    companion classifier, keeping this boundary deterministic and receipt-safe.
    """
    if not isinstance(item, dict):
        raise TypeError("LinkedIn inbound item must be a dictionary")
    source_id = item.get("provider_event_id") or item.get("message_id") or item.get("source_id") or item.get("id")
    thread_key = item.get("provider_conversation_id") or item.get("conversation_id") or item.get("thread_key")
    sender = str(item.get("sender") or item.get("sender_name") or item.get("from") or "")
    subject = str(item.get("subject") or item.get("subject_or_location") or "LinkedIn message")
    body = str(item.get("body_preview") or item.get("message") or item.get("text") or "")
    evidence_ref = str(item.get("evidence_ref") or item.get("raw_evidence_ref") or "")
    return MirrorEvent(
        surface="linkedin_messages",
        source_type="direct",
        source_timestamp=item.get("source_timestamp") or item.get("timestamp"),
        direction="inbound",
        sender=sender,
        participants=[str(value) for value in (item.get("participants") or []) if value],
        thread_key=str(thread_key) if thread_key else None,
        source_id=str(source_id) if source_id else None,
        subject_or_location=subject,
        body_preview=body,
        raw_evidence_ref=evidence_ref,
        trust_class="receipt_safe" if source_id or thread_key else "unverified",
        coverage_state=str(item.get("coverage_state") or "clean"),
        metadata={"adapter": "linkedin_inbound_v1"},
    )


def classify_linkedin_inbound_item(
    item: dict[str, Any], *, entity_candidates: list[tuple[str, list[str]]] | None = None
) -> dict[str, Any]:
    """Return a fail-closed commercial hand-off proposal for one LinkedIn item.

    This is a pure adapter: it performs no CRM, SharePoint, alert, ledger, or
    destination-writer call.  A commercial item can *propose* those routes; an
    unmapped entity always remains ``proposal_pending_review`` for a human to
    attribute before any destination write.
    """
    event = normalize_linkedin_inbound_item(item)
    result: dict[str, Any] = {
        "event": event,
        "event_dict": event_to_dict(event),
        "route_set": [],
        "classification": "not_commercial",
        "closure_state": "not_needed",
        "entity_state": "not_applicable",
        "entity_refs": [],
        "commercial_evidence": [],
        "destination_writer_invoked": False,
    }
    if not event.has_receipt_safe_identity:
        result.update({
            "classification": "coverage_incomplete",
            "closure_state": "coverage_incomplete",
            "entity_state": "unverified",
            "review_reason": "LinkedIn item lacks both provider message and conversation identifiers",
        })
        return result
    if event.coverage_state in {"incomplete", "coverage_incomplete"}:
        result.update({
            "classification": "coverage_incomplete",
            "closure_state": "coverage_incomplete",
            "entity_state": "unverified",
            "review_reason": "LinkedIn source coverage is incomplete",
        })
        return result

    lower = event.combined_text.lower()
    evidence = sorted({term for term in LINKEDIN_COMMERCIAL_TERMS if term in lower})
    if not evidence:
        return result

    # No fallback file read: entity candidates are an explicit input to this
    # adapter.  Missing/ambiguous attribution is a review condition, never a
    # reason to guess an existing CRM record or invoke a writer.
    entities = known_entity_hits(event.combined_text, entity_candidates or [])
    result.update({
        "classification": "commercial_lead",
        "commercial_evidence": evidence,
        "route_set": ["alert", "crm", "sharepoint"],
        "entity_refs": entities,
    })
    if len(entities) == 1:
        result.update({
            "entity_state": "mapped",
            "closure_state": "commercial_routing_proposed",
            "review_reason": "Commercial relevance is evidenced; destination writes remain outside this pure adapter",
        })
    else:
        result.update({
            "entity_state": "ambiguous" if len(entities) > 1 else "unmapped",
            "closure_state": "proposal_pending_review",
            "review_reason": "Resolve commercial entity attribution before CRM or SharePoint destination writing",
        })
    return result


# Explicit alias for pollers/adapters that prefer verb-first naming.
adapt_linkedin_inbound_item = classify_linkedin_inbound_item


def event_to_dict(event: MirrorEvent) -> dict[str, Any]:
    return {
        "surface": event.surface,
        "source_type": event.source_type,
        "source_timestamp": event.source_timestamp,
        "direction": event.direction,
        "sender": event.sender,
        "participants": event.participants,
        "thread_key": event.thread_key,
        "source_id": event.source_id,
        "subject_or_location": event.subject_or_location,
        "body_preview": event.body_preview,
        "raw_evidence_ref": event.raw_evidence_ref,
        "trust_class": event.trust_class,
        "coverage_state": event.coverage_state,
        "metadata": event.metadata,
        "stable_item_key": event.stable_item_key,
        "routing_status": "unclassified",
        "routing_flags": [],
        "management_relevance": "unassessed",
    }


def load_crm_entity_candidates(crm_path: Path = CRM_PATH) -> list[tuple[str, list[str]]]:
    """Load CRM entities that should trigger routing from mirror surfaces.

    Opportunities/accounts are always durable CRM entities. Lead rows are also
    relevant for inbound replies: if an external sender matches a lead's company,
    contact, email, or domain, the router should surface it for CRM handling
    rather than treating the lead table as invisible.

    The CRM file also contains campaign and pack snapshot tables whose first
    column can be short ids like C1/C2. Those are not entity sections and must not
    trigger CRM routing from arbitrary mirror text.
    """
    if not crm_path.exists():
        return []
    candidates: list[tuple[str, list[str]]] = []
    current_section = ""
    durable_sections = {"## Opportunities", "## Accounts"}
    lead_sections = {"## Leads", "## SJP Campaign Leads"}
    for line in crm_path.read_text(errors="ignore").splitlines():
        if line.startswith("## "):
            current_section = line.strip()
            continue
        if current_section not in durable_sections | lead_sections:
            continue
        if not line.startswith("|") or line.startswith("|---") or line.lower().startswith("| company"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if current_section in durable_sections:
            if len(cells) < 2:
                continue
            company = cells[0]
            contacts = cells[1]
            names = [company] + [part.strip() for part in re.split(r"/|,|;", contacts) if part.strip()]
            candidates.append((company, names))
            continue
        # Lead table columns:
        # Company | Domain | ICP | Location | Contact | Title | Email | ...
        if len(cells) < 7:
            continue
        company, domain, contact, email = cells[0], cells[1], cells[4], cells[6]
        tokens = [company]
        if contact and contact != "—":
            tokens.extend(part.strip() for part in re.split(r"/|,|;", contact) if part.strip() and part.strip() != "—")
        if email and email != "—":
            tokens.append(email)
        if domain and domain != "—" and "." in domain:
            tokens.append(domain)
        candidates.append((company, tokens))
    # Partnerships are equally durable commercial entities. Their omission was
    # a material routing defect: partner conversations could be visible but
    # never enter CRM/SharePoint reconciliation.
    if PARTNERSHIPS_PATH.exists():
        for line in PARTNERSHIPS_PATH.read_text(errors="ignore").splitlines():
            if not line.startswith("|") or line.startswith("|---") or line.lower().startswith("| name"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 2:
                continue
            name, contacts = cells[0], cells[1]
            if not name or name in {"—", "Name"}:
                continue
            tokens = [name] + [part.strip() for part in re.split(r"/|,|;", contacts) if part.strip() and part.strip() != "—"]
            candidates.append((name, tokens))
    return candidates


def known_entity_hits(text: str, candidates: list[tuple[str, list[str]]] | None = None) -> list[str]:
    haystack = text.lower()
    hits: list[str] = []
    for company, names in candidates or load_crm_entity_candidates():
        for name in names:
            if not name or len(name) <= 3:
                continue
            if re.search(rf"\b{re.escape(name.lower())}\b", haystack):
                hits.append(company)
                break
    return sorted(set(hits))


def load_live_crm_entity_types(crm_path: Path = CRM_PATH) -> dict[str, str]:
    """Return only Account/Opportunity entity kinds for commitment admission.

    Leads and partnerships can still use the ordinary CRM path. A visible
    outbound WhatsApp commitment is eligible for the stronger maintenance
    contract only when its recipient maps deterministically to a live Account
    or Opportunity.
    """
    if not crm_path.exists():
        return {}
    types: dict[str, str] = {}
    section_to_kind = {"## Accounts": "Account", "## Opportunities": "Opportunity"}
    current_kind: str | None = None
    for line in crm_path.read_text(errors="ignore").splitlines():
        if line.startswith("## "):
            current_kind = section_to_kind.get(line.strip())
            continue
        if not current_kind or not line.startswith("|") or line.startswith("|---") or line.lower().startswith("| company"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0] and cells[0] != "—":
            types[cells[0]] = current_kind
    return types


def medium_policy(event: MirrorEvent) -> dict[str, Any]:
    """Return thresholds/tuning for a surface without changing core flag semantics."""
    if event.surface == "teams_recent":
        return {
            "direct_thread_types": {"chat"},
            "groupish_thread_types": {"channel"},
            "channel_requires_signal": True,
            "outbound_context_self_names": {"tom dean", "tom", "l1", "assistant", "tom dean-pa"},
        }
    if event.surface == "whatsapp_recent":
        return {
            "direct_thread_types": {"direct"},
            "groupish_thread_types": {"group"},
            "channel_requires_signal": True,
            "outbound_context_self_names": {"me", "tom", "tom dean"},
        }
    if event.surface.endswith("_external"):
        return {"external_sender": True, "channel_requires_signal": False}
    return {"channel_requires_signal": False}


def invoice_or_expense_flags(event: MirrorEvent, entities: list[str]) -> tuple[set[str], str | None]:
    """Separate supplier-cost signals from customer receivables without guessing.

    A bare invoice mention is an invoice-management signal, not an expense. It
    becomes an expense only with stronger cost evidence. Ambiguous cases remain
    invoice-owned for review instead of polluting the expense ledger.
    """
    lower = event.combined_text.lower()
    has_invoice = any(term in lower for term in INVOICE_TERMS)
    has_cost_signal = any(term in lower for term in EXPENSE_TERMS + VENDOR_COST_TERMS)
    if not has_invoice and not has_cost_signal:
        return set(), None
    client_receivable = bool(entities) or event.direction in {"outbound", "self"} or bool(re.search(r"\binv[- ]?\d+\b", lower))
    if has_cost_signal and not client_receivable:
        return {"EXPENSE"}, "supplier-cost evidence detected"
    if has_invoice:
        return {"INVOICE"}, "invoice/receivable signal detected; supplier-cost classification requires stronger evidence" if not has_cost_signal else "commercial invoice signal detected"
    return {"EXPENSE"}, "expense evidence detected"


def is_provider_classified_automated_email(event: MirrorEvent, sender_address: str) -> bool:
    """Return true only for explicit provider automation metadata or a machine sender.

    This is a suppression decision, so ambiguity must remain draft-admitted. Do
    not infer automation from an email subject/body: both are untrusted content.
    """
    metadata = event.metadata or {}
    if metadata.get("is_automated") is True or metadata.get("message_class") in {"system", "bounce", "calendar"}:
        return True
    localpart = sender_address.split("@", 1)[0] if "@" in sender_address else ""
    return bool(AUTOMATED_SENDER_LOCALPART_RE.fullmatch(localpart))


def route_contract(flags: set[str], *, closure_state: str, entities: list[str], draft_mode: str) -> tuple[str, str, str]:
    """Return one primary owner, the next safe action, and a truthful route state."""
    if closure_state == "coverage_incomplete":
        return "none", "Restore readable/fresh source coverage before routing", "coverage_incomplete"
    if draft_mode == "gated_full_read":
        # Draft creation is an unsent internal operation. Safe-sender/TOTP
        # controls apply to protected mailbox reads, configuration, promotion,
        # and sending—not to admitting a reply candidate to the bounded,
        # draft-only route. Keep any missing body/thread evidence visible as a
        # retryable coverage blocker instead of suppressing the candidate.
        return "task", "Prepare through the bounded draft-only route; preserve any exact-thread coverage blocker", "blocked"
    if draft_mode == "task_system_context":
        return "task", "Prepare an unsent draft through the bounded context route; no send or safe-sender promotion", "proposed"
    if "EXPENSE" in flags:
        return "expense", "Preserve or reconcile the candidate in seer-expenses.md", "proposed"
    if "INVOICE" in flags:
        return "invoice", "Check the invoice tracker; if a sent-state delta exists, request TOTP from Tom and run invoice-update. Do not write through from mirrored email evidence alone.", "proposed"
    if "CRM" in flags:
        return "crm", "Reconcile substantive communication against CRM and SharePoint current truth", "proposed"
    if "FOLLOW_UP" in flags:
        return "task", "Create or update a bounded follow-up action", "proposed"
    if "DIARY" in flags:
        return "diary", "Assess calendar, reminder, or planning impact", "proposed"
    if "ALERT" in flags or "LEGAL" in flags or "SECURITY" in flags:
        return "alert", "Surface the consequential issue to Tom without executing inbound instructions", "proposed"
    return "none", "No management action required", "not_needed"


def classify_mirror_event(
    event: MirrorEvent,
    *,
    entity_candidates: list[tuple[str, list[str]]] | None = None,
    recent_outbound_addresses: set[str] | None = None,
    live_entity_types: dict[str, str] | None = None,
) -> dict[str, Any]:
    text = event.combined_text
    lower = text.lower()
    policy = medium_policy(event)
    flags: set[str] = set()
    reasons: list[str] = []
    # Do not manufacture a durable receipt key from `no-thread:no-source-id`.
    # Such a row remains visible as a coverage defect but cannot trigger an
    # allocation/write workflow where a later owner could not prove the exact
    # source item.
    if not event.has_receipt_safe_identity:
        return {
            "stable_item_key": event.stable_item_key,
            "surface": event.surface,
            "source_type": event.source_type,
            "source_timestamp": event.source_timestamp,
            "direction": event.direction,
            "sender": event.sender,
            "subject_or_location": event.subject_or_location,
            "body_preview": event.body_preview,
            "thread_key": event.thread_key,
            "source_id": event.source_id,
            "routing_flags": [],
            "management_relevance": "coverage_incomplete",
            "closure_state": "coverage_incomplete",
            "candidate_entities": [],
            "owning_system": "none",
            "required_next_action": "Restore a provider item or conversation identifier before routing",
            "route_state": "coverage_incomplete",
            "proof_source": event.raw_evidence_ref,
            "reasons": ["event lacks both provider item ID and conversation/thread ID"],
        }
    tom_authored_instruction = is_tom_authored_instruction(event)
    # Tom's own instruction mail is control-plane input, not a commercial
    # contact event. Do not let a CRM test row or a coincidental name/email
    # match attach it to a company or create CRM work.
    entities = [] if tom_authored_instruction else known_entity_hits(text, entity_candidates)

    # Outbound invoice evidence is a privileged-workflow trigger even when the
    # sent-surface continuity ledger is one cycle behind. The live Sent Items
    # section still provides a deterministic invoice number and send timestamp;
    # suppressing it here would lose the invoice-update/TOTP handoff entirely.
    outbound_invoice_signal = bool(
        event.direction == "outbound"
        and event.surface in {"assistant_sent", "microsoft_sent"}
        and re.search(r"\binv[- ]?\d+\b", lower)
    )
    if event.coverage_state in {"incomplete", "coverage_incomplete"} and not outbound_invoice_signal:
        return {
            "stable_item_key": event.stable_item_key,
            "surface": event.surface,
            "source_type": event.source_type,
            "source_timestamp": event.source_timestamp,
            "direction": event.direction,
            "sender": event.sender,
            "subject_or_location": event.subject_or_location,
            "body_preview": event.body_preview,
            "thread_key": event.thread_key,
            "source_id": event.source_id,
            "routing_flags": [],
            "management_relevance": "coverage_incomplete",
            "closure_state": "coverage_incomplete",
            "candidate_entities": [],
            "owning_system": "none",
            "required_next_action": "Restore readable/fresh source coverage before routing",
            "route_state": "coverage_incomplete",
            "proof_source": event.raw_evidence_ref,
            "reasons": ["source coverage incomplete"],
        }

    # LinkedIn messages authored by Tom are outbound thread context, never an
    # inbound reply. Their wording may legitimately contain commercial or
    # follow-up terms, but must not create a CRM/follow-up proposal until a
    # distinct inbound LinkedIn message is captured with direction=inbound.
    if event.surface == "linkedin_messages" and event.direction in {"outbound", "self"}:
        return {
            "stable_item_key": event.stable_item_key,
            "surface": event.surface,
            "source_type": event.source_type,
            "source_timestamp": event.source_timestamp,
            "direction": event.direction,
            "sender": event.sender,
            "subject_or_location": event.subject_or_location,
            "body_preview": event.body_preview,
            "thread_key": event.thread_key,
            "source_id": event.source_id,
            "routing_flags": ["OUTBOUND_CONTEXT"],
            "management_relevance": "not_needed",
            "closure_state": "not_needed",
            "candidate_entities": [],
            "owning_system": "none",
            "required_next_action": "Await a separately captured inbound LinkedIn reply before creating a proposal",
            "route_state": "not_needed",
            "proof_source": event.raw_evidence_ref,
            "reasons": ["outbound/self LinkedIn item is context only and cannot be surfaced as a recipient reply"],
        }

    # Direct WhatsApp outbound messages have a recipient-bearing source line
    # (for example `Tom -> Stuart`). A commitment is a first-class commercial
    # state signal, even when its recipient cannot safely be mapped: the latter
    # must create blocked CRM maintenance rather than falling back to TASKS.
    is_direct_outbound_whatsapp = (
        event.surface == "whatsapp_recent"
        and event.source_type == "direct"
        and event.direction in {"outbound", "self"}
    )
    outbound_commitment = bool(
        is_direct_outbound_whatsapp
        and (
            (OUTBOUND_COMMITMENT_PROMISE_RE.search(event.body_preview) and OUTBOUND_COMMITMENT_DELIVERABLE_RE.search(event.body_preview))
            or OUTBOUND_COMMITMENT_CONTROL_RE.search(event.body_preview)
        )
    )
    entity_types = live_entity_types if live_entity_types is not None else load_live_crm_entity_types()
    mapped_entity_type = entity_types.get(entities[0]) if len(entities) == 1 else None

    if tom_authored_instruction:
        flags.add("FOLLOW_UP")
        reasons.append("Tom-authored direct instruction detected; route as L1 work, not CRM activity")
    elif entities:
        flags.add("CRM")
        reasons.append("known CRM/account/opportunity/partner name detected")
    if outbound_commitment:
        flags.add("CRM")
        reasons.append("outbound direct WhatsApp commitment/deliverable detected; CRM+SharePoint maintenance is required")
    if any(term in lower for term in FOLLOW_UP_TERMS):
        flags.add("FOLLOW_UP")
        reasons.append("action/follow-up/status language detected")
    if DATE_TIME_RE.search(lower):
        flags.add("DIARY")
        reasons.append("date/time/planning language detected")
    money_flags, money_reason = invoice_or_expense_flags(event, entities)
    flags.update(money_flags)
    if money_reason:
        reasons.append(money_reason)
    if any(re.search(rf"\b{re.escape(term)}\b", lower) for term in LEGAL_TERMS):
        flags.add("LEGAL")
        reasons.append("legal/admin-risk language detected")
    if any(re.search(rf"\b{re.escape(term)}\b", lower) for term in SECURITY_TERMS):
        flags.add("SECURITY")
        reasons.append("security/access language detected")
    groupish = event.source_type in set(policy.get("groupish_thread_types", set()))
    if groupish:
        # Group/channel mirrors are noisy. Keep strong CRM/expense signals, but
        # suppress generic date/security/legal/follow-up words unless they carry
        # a real management signal.
        if "DIARY" in flags and not (flags & {"CRM", "FOLLOW_UP", "EXPENSE"}):
            flags.discard("DIARY")
            reasons.append("group/channel date wording suppressed as low-value without stronger signal")
        if "SECURITY" in flags and not any(term in lower for term in ["password", "mfa", "2fa", "breach", "login", "reset", "verification code"]):
            flags.discard("SECURITY")
            reasons.append("generic security/cybersecurity wording suppressed in group/channel context")
        if "LEGAL" in flags and "claim to fame" in lower:
            flags.discard("LEGAL")
            reasons.append("idiomatic 'claim to fame' suppressed as non-legal")
        directed_at_tom = bool(re.search(r"\b(tom|tom dean|@tom)\b", lower))
        strong_group_followup = any(term in lower for term in ["blocked", "retest", "bug", "build", "invoice", "payment"])
        if "FOLLOW_UP" in flags and not (directed_at_tom or flags & {"CRM", "EXPENSE"} or strong_group_followup):
            flags.discard("FOLLOW_UP")
            reasons.append("group/channel follow-up wording suppressed because it is not directed at Tom and has no stronger management signal")

    if any(term in lower for term in ALERT_TERMS) and (flags & {"CRM", "FOLLOW_UP", "LEGAL", "SECURITY"}):
        flags.add("ALERT")
        reasons.append("urgent/blocking wording on managed item")

    context_only_flags: set[str] = set()
    if event.direction in {"outbound", "self"}:
        context_only_flags.add("OUTBOUND_CONTEXT")
        reasons.append("self/outbound message is thread-state evidence, but not sufficient by itself")

    management_flags = flags.copy()
    all_flags = flags | context_only_flags
    is_email_surface = event.surface in {
        "microsoft_inbox",
        "microsoft_external",
        "assistant_inbox",
        "assistant_external",
        "gmail_inbox",
        "gmail_external",
        "assistant_sent",
        "microsoft_sent",
    }
    trusted_email_path = event.surface in {"microsoft_inbox", "assistant_inbox", "gmail_inbox"} and event.direction == "inbound"
    external_email_path = event.surface in {"microsoft_external", "assistant_external", "gmail_external"} and event.direction == "inbound"
    sender_match = EMAIL_ADDRESS_RE.search(event.sender)
    sender_address = sender_match.group(0).lower() if sender_match else ""
    prior_outbound_contact = bool(external_email_path and sender_address and sender_address in (recent_outbound_addresses or set()))
    scheduling_commercial_signal = bool(SCHEDULING_COMMERCIAL_RE.search(event.subject_or_location))
    if prior_outbound_contact and scheduling_commercial_signal:
        # A real recipient-linked scheduling/commercial update can be reply-worthy
        # even where the external mirror withholds the body and the subject lacks
        # an explicit question. Admit it to the no-send bounded draft path; do not
        # infer content or send anything.
        flags.add("FOLLOW_UP")
        management_flags = flags.copy()
        all_flags = flags | context_only_flags
        reasons.append("external scheduling/commercial update from a recent outbound contact")

    # Default-to-draft policy for fresh inbound email: do not make a human
    # correspondent prove reply-worthiness through keywords, a question mark or
    # CRM matching. This is only task/draft admission, never send authority.
    # Suppression is limited to explicit provider automation metadata, an
    # unambiguous machine sender, or a transactional receipt/invoice with no
    # independent response signal. Ambiguity remains admitted for Tom review.
    explicit_response_signal = "FOLLOW_UP" in management_flags
    transactional_notification = bool(
        is_email_surface
        and event.direction == "inbound"
        and (flags & {"EXPENSE", "INVOICE"})
        and not explicit_response_signal
    )
    automated_email = bool(
        is_email_surface
        and event.direction == "inbound"
        and (is_provider_classified_automated_email(event, sender_address) or transactional_notification)
    )
    likely_reply = bool(is_email_surface and event.direction == "inbound" and not automated_email)
    if likely_reply:
        flags.add("FOLLOW_UP")
        management_flags = flags.copy()
        all_flags = flags | context_only_flags
        reasons.append("default-to-draft admission for fresh inbound human/unknown email")
    elif automated_email:
        reasons.append("automatic suppression: provider/machine classification or a transactional receipt/invoice without a response signal")
    reply_likelihood = "likely" if likely_reply else "none"
    readability_strength = "trusted_preview" if trusted_email_path else ("external_withheld" if external_email_path else "n/a")
    task_system_candidate = bool(
        is_email_surface
        and event.direction == "inbound"
        and (likely_reply or tom_authored_instruction)
    )
    task_system_reason = None
    if task_system_candidate:
        task_system_reason = (
            "Tom-authored instruction requires an explicit L1 reply-prep path"
            if tom_authored_instruction
            else "default-to-draft candidate; exact thread and policy-bound context determine whether an unsent draft can be created"
        )
        reasons.append("task-system context assembly candidate")
    promotion_candidate = bool(external_email_path and likely_reply and ("CRM" in management_flags or len(entities) > 0))
    promotion_reason = None
    if promotion_candidate:
        promotion_reason = "external sender appears consequential enough that stronger read access may help future reply handling"
        reasons.append("approved-sender promotion candidate")
    draft_mode = "none"
    if likely_reply and trusted_email_path:
        draft_mode = "direct_trusted"
        reasons.append("trusted inbox path is readable enough for direct draft preparation")
    elif likely_reply and external_email_path:
        # External/non-safe-list status must not prevent unsent draft
        # preparation. The bounded external reader/task route decides whether
        # the exact thread is readable; if not, it records coverage_incomplete
        # and retries/escalates visibly rather than dropping the reply.
        draft_mode = "task_system_context"
        reasons.append("external reply candidate admitted to draft-only context route; safe-sender status affects send/read gates, not draft admission")
    elif task_system_candidate:
        draft_mode = "task_system_context"
    if task_system_candidate and draft_mode == "direct_trusted":
        draft_mode = "task_system_context"
        reasons.append("trusted path is readable, but richer context assembly is preferred before drafting")

    # Group/channel surfaces need a real signal; otherwise suppress by default.
    if policy.get("channel_requires_signal") and event.source_type in set(policy.get("groupish_thread_types", set())) and not management_flags:
        relevance = "not_needed"
        closure_state = "not_needed"
    elif management_flags:
        relevance = "needs_management"
        closure_state = "blocked" if draft_mode == "gated_full_read" else "classified"
    else:
        relevance = "not_needed"
        closure_state = "not_needed"

    owning_system, required_next_action, route_state = route_contract(
        management_flags, closure_state=closure_state, entities=entities, draft_mode=draft_mode
    )
    # CRM capture may proceed only with exactly one deterministic entity. A
    # multi-hit record is preserved but blocked rather than silently assigned.
    # The commitment route is stricter: only a live Account/Opportunity mapping
    # can be queued; lead/partner/untyped matches fail closed for review.
    crm_capture_state = "not_applicable"
    crm_capture_blocker = None
    if "CRM" in management_flags and relevance == "needs_management":
        if len(entities) == 1 and (not outbound_commitment or mapped_entity_type in {"Account", "Opportunity"}):
            crm_capture_state = "queued" if outbound_commitment else "pending"
        elif len(entities) > 1:
            crm_capture_state = "blocked"
            crm_capture_blocker = "multiple candidate entities; resolve attribution before CRM/SharePoint write"
        elif outbound_commitment:
            crm_capture_state = "blocked"
            crm_capture_blocker = "outbound WhatsApp commitment has no deterministic live Account/Opportunity mapping"
        else:
            crm_capture_state = "blocked"
            crm_capture_blocker = "CRM signal has no deterministic entity"

    source_line_ref = str(event.metadata.get("source_line_ref") or event.raw_evidence_ref or event.stable_item_key)
    commitment_control = {
        "detected": outbound_commitment,
        "last_touch_date": (event.source_timestamp or "")[:10] or None,
        "next_action": "Reconcile Tom's stated commitment; confirm the deliverable/next step and update CRM control facts.",
        "owner": "Tom",
        "sharepoint_requirement": "Update SharePoint Current and create/link a dated communication or commitment artifact; retain write proof.",
    }
    entity_mapping = {
        "status": "mapped" if len(entities) == 1 and mapped_entity_type in {"Account", "Opportunity"} else ("ambiguous" if len(entities) > 1 else "unmapped"),
        "entity": entities[0] if len(entities) == 1 else None,
        "entity_type": mapped_entity_type,
        "candidates": entities,
    }

    return {
        "stable_item_key": event.stable_item_key,
        "surface": event.surface,
        "source_type": event.source_type,
        "source_timestamp": event.source_timestamp,
        "direction": event.direction,
        "sender": event.sender,
        "subject_or_location": event.subject_or_location,
        "body_preview": event.body_preview,
        "thread_key": event.thread_key,
        "source_id": event.source_id,
        "routing_flags": sorted(all_flags),
        "management_relevance": relevance,
        "closure_state": closure_state,
        "candidate_entities": entities,
        "owning_system": owning_system,
        "required_next_action": required_next_action,
        "route_state": route_state,
        "proof_source": event.raw_evidence_ref,
        "reasons": reasons,
        "reply_likelihood": reply_likelihood,
        "reply_decision": "reply_needed" if likely_reply else ("blocked_to_decide" if reply_likelihood == "maybe" else "no_reply_needed"),
        "reply_decision_reason": "Reply signal is present in the bounded routed event." if likely_reply else ("Potentially consequential inbound requires bounded evidence/review." if reply_likelihood == "maybe" else "No reply signal identified in the routed event."),
        "draft_mode": draft_mode,
        "readability_strength": readability_strength,
        "promotion_candidate": promotion_candidate,
        "promotion_reason": promotion_reason,
        "task_system_candidate": task_system_candidate,
        "task_system_reason": task_system_reason,
        "crm_capture_state": crm_capture_state,
        "crm_capture_blocker": crm_capture_blocker,
        "entity_mapping": entity_mapping,
        "source_line_ref": source_line_ref,
        "outbound_commitment_control": commitment_control,
    }


def load_events_from_json_feed(path: Path) -> tuple[dict[str, Any], list[MirrorEvent]]:
    payload = json.loads(path.read_text(errors="ignore") or "{}")
    coverage_state = payload.get("coverage_state") or "clean"
    events: list[MirrorEvent] = []
    for raw in payload.get("items") or []:
        event = event_from_dict(raw)
        if not event.coverage_state:
            event.coverage_state = coverage_state
        events.append(event)
    return payload, events


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

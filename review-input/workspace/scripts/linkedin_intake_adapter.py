#!/usr/bin/env python3
"""Receipt-safe, internal-only LinkedIn commercial-lead intake fixture adapter.

This is deliberately not wired to a LinkedIn mirror or destination worker.  It
normalises one caller-provided fixture, persists only to a caller-provided
internal ledger root, and creates review receipts.  It never reads/writes CRM,
SharePoint, alerts, or any external service.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import intake_ledger as ledger
from mirror_router import classify_linkedin_inbound_item

SURFACE = "linkedin_messages"
COMMERCIAL_TERMS = (
    "consulting",
    "proposal",
    "quote",
    "project",
    "scope",
    "requirements",
    "budget",
    "demo",
    "discovery call",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalise_linkedin_fixture(
    fixture: dict[str, Any], *, entity_candidates: list[tuple[str, list[str]]] | None = None
) -> dict[str, Any]:

    """Convert one supplied LinkedIn fixture to the canonical event payload.

    The caller must supply a provider message or conversation ID.  There is no
    inference from a name/body: identityless material cannot become a lead.
    """
    if not isinstance(fixture, dict):
        raise TypeError("LinkedIn fixture must be a dictionary")
    provider_event_id = _text(fixture.get("provider_event_id") or fixture.get("message_id") or fixture.get("id")) or None
    provider_conversation_id = _text(
        fixture.get("provider_conversation_id") or fixture.get("conversation_id") or fixture.get("thread_id")
    ) or None
    if not provider_event_id and not provider_conversation_id:
        raise ValueError("LinkedIn fixture requires provider_event_id or provider_conversation_id")

    message = _text(fixture.get("message") or fixture.get("body") or fixture.get("text"))
    source_timestamp = _text(fixture.get("source_timestamp") or fixture.get("timestamp"))
    observed_at = _text(fixture.get("observed_at"))
    evidence_ref = _text(fixture.get("evidence_ref"))
    if not source_timestamp or not observed_at or not evidence_ref:
        raise ValueError("LinkedIn fixture requires source_timestamp, observed_at, and evidence_ref")

    commercial_evidence = sorted(term for term in COMMERCIAL_TERMS if term in message.lower())
    if not commercial_evidence:
        raise ValueError("LinkedIn fixture does not contain deterministic commercial evidence")

    # Mapping is deterministic and caller-bounded: the adapter never reads CRM
    # state, guesses an entity, or treats a fixture-provided entity name as one.
    # The shared classifier is also the receipt-safety gate for this vertical
    # slice, so only a classified commercial event reaches the ledger.
    routing = classify_linkedin_inbound_item(
        {
            "provider_event_id": provider_event_id,
            "provider_conversation_id": provider_conversation_id,
            "sender_name": _text(fixture.get("sender_name") or fixture.get("sender")),
            "subject": _text(fixture.get("subject")),
            "message": message,
            "source_timestamp": source_timestamp,
            "evidence_ref": evidence_ref,
            "coverage_state": _text(fixture.get("coverage_state")) or "clean",
        },
        entity_candidates=entity_candidates,
    )
    if routing["classification"] != "commercial_lead" or routing["entity_state"] == "unverified":
        raise ValueError("LinkedIn fixture is not a receipt-safe commercial event")

    entity_refs = list(routing["entity_refs"])
    entity_state = "mapped" if routing["entity_state"] == "mapped" else "unmapped_review_required"
    return {
        "surface": SURFACE,
        "provider_event_id": provider_event_id,
        "provider_conversation_id": provider_conversation_id,
        "source_timestamp": source_timestamp,
        "observed_at": observed_at,
        "evidence_refs": [evidence_ref],
        "identity_state": "receipt_safe",
        "classification": "commercial_lead",
        "confidence": "high",
        "entity_state": entity_state,
        "entity_refs": entity_refs,
        "route_set": ["alert", "crm", "sharepoint"],
        "adapter_metadata": {
            "adapter": "linkedin_intake_fixture_v1",
            "commercial_evidence": commercial_evidence,
            "sender_name": _text(fixture.get("sender_name") or fixture.get("sender")),
            "entity_mapping": routing["entity_state"],
            "external_writes": False,
            "automatic_entity_creation": False,
        },
    }


def build_internal_receipts(
    event_id: str, evidence_ref: str, next_review_at: str, *, entity_state: str = "unmapped_review_required"
) -> list[dict[str, Any]]:
    """Return canonical internal receipts without invoking destination writers.

    Alert review is always pending. CRM and SharePoint are pending only for one
    deterministic mapping; an unmapped/ambiguous event stays explicitly blocked.
    """
    if not _text(event_id) or not _text(evidence_ref) or not _text(next_review_at):
        raise ValueError("event_id, evidence_ref, and next_review_at are required")
    mapped = entity_state == "mapped"
    destination_state = "pending" if mapped else "blocked"
    destination_error = None if mapped else "entity_mapping_required"
    return [
        {
            "event_id": event_id,
            "route": "alert",
            "state": "pending",
            "owner": "internal-alert-review",
            "evidence_ref": evidence_ref,
            "destination_ref": None,
            "error_code": None,
            "next_review_at": next_review_at,
        },
        {
            "event_id": event_id,
            "route": "crm",
            "state": destination_state,
            "owner": "crm-review",
            "evidence_ref": evidence_ref,
            "destination_ref": None,
            "error_code": destination_error,
            "next_review_at": next_review_at,
        },
        {
            "event_id": event_id,
            "route": "sharepoint",
            "state": destination_state,
            "owner": "sharepoint-review",
            "evidence_ref": evidence_ref,
            "destination_ref": None,
            "error_code": destination_error,
            "next_review_at": next_review_at,
        },
    ]


def record_linkedin_fixture(
    fixture: dict[str, Any], *, root: Path, entity_candidates: list[tuple[str, list[str]]] | None = None
) -> dict[str, Any]:
    """Persist one canonical event and its internal-only review receipts.

    ``root`` is mandatory so this helper cannot silently write to the live
    workspace ledger.  The returned records are ledger receipts only.
    """
    if not isinstance(root, Path):
        root = Path(root)
    event_payload = normalise_linkedin_fixture(fixture, entity_candidates=entity_candidates)
    event, event_created = ledger.record_event(event_payload, root=root)
    evidence_ref = event_payload["evidence_refs"][0]
    next_review_at = _text(fixture.get("next_review_at") or event_payload["observed_at"])
    receipts = []
    for receipt in build_internal_receipts(
        event["event_id"], evidence_ref, next_review_at, entity_state=event_payload["entity_state"]
    ):
        recorded, created = ledger.record_receipt(receipt, root=root)
        receipts.append({**recorded, "created": created})
    return {"event": event, "event_created": event_created, "receipts": receipts}

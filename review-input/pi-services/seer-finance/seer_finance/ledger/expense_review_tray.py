"""Read-only review-snapshot builder for the SEER expense operational ledger.

This is deliberately a presentation/foundation layer over a dry-run import manifest.
It neither changes a manifest classification nor writes a ledger, queue, database, or
source.  A future authenticated internal Control Panel may consume its JSON snapshot.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

QUEUE_EVIDENCE_SUPPORTED = "evidence_supported_ready_to_validate"
QUEUE_NEEDS_DECISION = "needs_decision"
QUEUE_EVIDENCE_GAP = "evidence_gap"
QUEUE_NAMES = (QUEUE_EVIDENCE_SUPPORTED, QUEUE_NEEDS_DECISION, QUEUE_EVIDENCE_GAP)
_FORBIDDEN_ACTIONS = {"--apply", "--write", "--cutover", "--action"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any, length: int = 24) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()[:length]


def _manifest_from(value: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    path = Path(value)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("review manifest must be a JSON object")
    return loaded


def manifest_identity(manifest: dict[str, Any] | str | Path) -> dict[str, str]:
    """Return stable identity/checksums used to reject a stale review snapshot."""
    source = _manifest_from(manifest)
    inputs = source.get("inputs")
    report_checksum = _digest(source, 64)
    input_checksums: dict[str, str] = {}
    if isinstance(inputs, dict):
        for name, item in sorted(inputs.items()):
            if isinstance(item, dict) and isinstance(item.get("sha256"), str):
                input_checksums[str(name)] = item["sha256"]
    return {
        "manifest_identity": _digest({"manifest_version": source.get("manifest_version"), "inputs": input_checksums, "records": source.get("records", [])}),
        "report_checksum": report_checksum,
    }


def _source_checksum(record: dict[str, Any], input_checksums: dict[str, str]) -> str:
    source = str(record.get("source", "unknown"))
    # Imported manifests use source aliases which intentionally differ from input keys.
    aliases = {"transactions_json": "transactions_json", "seer_expenses_markdown": "seer_expenses_markdown", "expense_enrichment_queue": "expense_enrichment_queue", "tide_reconciliation": "tide_reconciliation"}
    return input_checksums.get(aliases.get(source, source), _digest(record.get("original"), 64))


def _record_ref(record: dict[str, Any]) -> str | None:
    candidate = record.get("candidate")
    if isinstance(candidate, dict) and isinstance(candidate.get("source_ref"), str):
        return candidate["source_ref"]
    value = record.get("original_source_ref")
    return value if isinstance(value, str) and value else None


def _needs_evidence(record: dict[str, Any]) -> bool:
    reason = str(record.get("reason") or "").lower()
    return record.get("classification") == "blocked" or any(word in reason for word in ("missing", "no stable", "parse", "ambiguous"))


def _queue_for(record: dict[str, Any], duplicated: bool) -> str:
    if duplicated:
        return QUEUE_NEEDS_DECISION
    if _needs_evidence(record):
        return QUEUE_EVIDENCE_GAP
    candidate = record.get("candidate")
    if record.get("classification") == "evidence_supported" or (isinstance(candidate, dict) and candidate.get("proposed_status") in {"ledger_written", "ledger_ready"}):
        return QUEUE_EVIDENCE_SUPPORTED
    return QUEUE_NEEDS_DECISION


def _prompts(record: dict[str, Any], queue: str, duplicated: bool) -> list[str]:
    if duplicated:
        return ["Choose whether these retained records are duplicates/conflicting records, and identify any record to retain separately."]
    if queue == QUEUE_EVIDENCE_GAP:
        return ["Provide or link the missing/ambiguous source evidence; do not infer financial facts."]
    candidate = record.get("candidate")
    if queue == QUEUE_NEEDS_DECISION and isinstance(candidate, dict) and candidate.get("proposed_status") == "needs_review":
        return ["Decide business or not-business from the retained source evidence.", "Choose a category only if supported by retained evidence."]
    return []


def build_review_snapshot(manifest: dict[str, Any] | str | Path) -> dict[str, Any]:
    """Build a deterministic, read-only review snapshot from a manifest dict or path."""
    source = _manifest_from(manifest)
    records = source.get("records", [])
    if not isinstance(records, list):
        raise ValueError("review manifest records must be an array")
    inputs = source.get("inputs") if isinstance(source.get("inputs"), dict) else {}
    checksums = {str(name): str(item["sha256"]) for name, item in inputs.items() if isinstance(item, dict) and isinstance(item.get("sha256"), str)}
    identity = manifest_identity(source)

    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if isinstance(record, dict) and (ref := _record_ref(record)):
            clusters[ref].append(record)
    duplicated_refs = {ref for ref, members in clusters.items() if len(members) > 1}

    queues: dict[str, list[dict[str, Any]]] = {name: [] for name in QUEUE_NAMES}
    review_records: list[dict[str, Any]] = []
    excluded_not_needed: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            record = {"source": "manifest", "source_location": "unknown", "classification": "blocked", "original": record, "reason": "manifest record is not an object"}
        if record.get("classification") == "not_needed":
            excluded_not_needed.append({
                "source": record.get("source"),
                "source_location": record.get("source_location"),
                "original_source_ref": record.get("original_source_ref"),
                "reason": record.get("reason"),
            })
            continue
        ref = _record_ref(record)
        duplicated = bool(ref and ref in duplicated_refs)
        source_checksum = _source_checksum(record, checksums)
        review_id = "rvw_" + _digest({"source": record.get("source"), "location": record.get("source_location"), "source_checksum": source_checksum})
        cluster_id = "cluster_" + _digest({"reference": ref, "members": [{"source": member.get("source"), "location": member.get("source_location"), "checksum": _source_checksum(member, checksums)} for member in clusters.get(ref, [])]}) if duplicated else None
        queue = _queue_for(record, duplicated)
        source_name = str(record.get("source", "unknown"))
        source_input = inputs.get({"transactions_json": "transactions_json", "seer_expenses_markdown": "seer_expenses_markdown", "expense_enrichment_queue": "expense_enrichment_queue", "tide_reconciliation": "tide_reconciliation"}.get(source_name, source_name))
        source_path = source_input.get("path") if isinstance(source_input, dict) else None
        item = {"review_id": review_id, "queue": queue, "source": record.get("source"), "source_path": source_path, "source_location": record.get("source_location"), "source_checksum": source_checksum, "original_source_ref": record.get("original_source_ref"), "retained_payload": copy.deepcopy(record.get("original")), "manifest_record": copy.deepcopy(record), "review_prompts": _prompts(record, queue, duplicated)}
        if cluster_id:
            item["duplicate_conflict_cluster_id"] = cluster_id
        queues[queue].append(item)
        review_records.append(item)

    cluster_output = []
    for ref in sorted(duplicated_refs):
        members = [item for item in review_records if _record_ref(item["manifest_record"]) == ref]
        cluster_output.append({"cluster_id": members[0]["duplicate_conflict_cluster_id"], "source_reference": ref, "members": [{"review_id": item["review_id"], "source": item["source"], "source_path": item["source_path"], "source_location": item["source_location"], "source_checksum": item["source_checksum"], "retained_payload": item["retained_payload"]} for item in members]})
    for queue in queues.values():
        queue.sort(key=lambda item: (str(item["source"]), str(item["source_location"]), item["review_id"]))
    return {"snapshot_version": 1, "mode": "read_only_review", "stale_review_protection": identity, "queue_definitions": {QUEUE_EVIDENCE_SUPPORTED: "evidence-supported records / ready-to-validate records; no posting is proposed", QUEUE_NEEDS_DECISION: "explicit reviewer decision required", QUEUE_EVIDENCE_GAP: "missing or ambiguous source evidence required"}, "queues": queues, "excluded_not_needed_audit": excluded_not_needed, "duplicate_conflict_clusters": cluster_output, "no_action_declaration": "Read-only snapshot only. It creates no classification, review decision, financial posting, persistence, or runtime action."}


def review_snapshot_is_current(snapshot: dict[str, Any], manifest: dict[str, Any] | str | Path) -> bool:
    """True only when the snapshot was built from the exact same manifest identity."""
    return snapshot.get("stale_review_protection") == manifest_identity(manifest)

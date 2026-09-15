"""Dry-run-only Phase 2 importer and reconciliation manifest for SEER expenses.

This module deliberately has no SQLite dependency and never writes source data. It
turns source records and optional Tide reconciliation evidence into auditable
proposals; evidence is never an accounting posting.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_CLASSIFICATIONS = {
    "imported_candidate", "exact_replay", "preserved_for_review", "blocked",
    "evidence_supported", "confirmed_classification_rule", "not_needed",
}

_STABLE_REF = re.compile(
    r"(?:invoice(?:\s+(?:no\.?|number))?|receipt|policy|order|confirmation)\s*"
    r"(?:no\.?|number|#)?\s*[`#:]?\s*([A-Za-z0-9][A-Za-z0-9-]{3,})", re.IGNORECASE,
)
_MARKDOWN_TABLE = re.compile(r"^\s*\|(.+)\|\s*$")
_SEPARATOR = re.compile(r"^\s*:?-{2,}:?\s*$")
_TIDE_RULE = re.compile(r"^\s*-\s+`(TIDE_[A-Z0-9_]+)`:\s*(.+)$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(source: str, location: str, classification: str, *, reason: str | None = None,
            source_ref: str | None = None, original: Any = None, candidate: Any = None) -> dict[str, Any]:
    if classification not in ALLOWED_CLASSIFICATIONS:
        raise ValueError(f"unsupported classification: {classification}")
    value: dict[str, Any] = {"source": source, "source_location": location,
        "classification": classification, "original_source_ref": source_ref,
        "reason": reason, "original": original}
    if candidate is not None:
        value["candidate"] = candidate
    return value


def _read_json(path: Path, expected: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"__parse_error__": f"{expected}: {exc}"}


def parse_transactions(path: Path) -> list[dict[str, Any]]:
    """Preserve every ledger array element, including malformed elements."""
    data = _read_json(path, "transactions")
    if not isinstance(data, list):
        return [_record("transactions_json", "$", "blocked", reason="top-level JSON value is not an array", original=data)]
    refs: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(data):
        if isinstance(row, dict) and isinstance(row.get("source_ref"), str) and row["source_ref"]:
            refs[row["source_ref"]].append(index)
    records: list[dict[str, Any]] = []
    for index, row in enumerate(data):
        location = f"$[{index}]"
        if not isinstance(row, dict):
            records.append(_record("transactions_json", location, "blocked", reason="ledger row is not an object", original=row))
            continue
        ref, txn_id = row.get("source_ref"), row.get("txn_id")
        if not isinstance(ref, str) or not ref:
            records.append(_record("transactions_json", location, "blocked", reason="missing stable source_ref", source_ref=ref, original=row))
        elif len(refs[ref]) > 1:
            records.append(_record("transactions_json", location, "preserved_for_review", reason="repeated legacy source_ref; every row retained without deduplication", source_ref=ref, original=row, candidate={"txn_id": txn_id, "source_ref": ref, "proposed_status": "needs_review"}))
        else:
            records.append(_record("transactions_json", location, "imported_candidate", source_ref=ref, original=row, candidate={"txn_id": txn_id, "source_ref": ref, "proposed_status": "ledger_written"}))
    return records


def _stable_ref(cells: list[str]) -> str | None:
    match = _STABLE_REF.search(" | ".join(cells))
    return match.group(1) if match else None


def parse_markdown(path: Path, known_ledger_refs: set[str]) -> list[dict[str, Any]]:
    """Parse table records only; prose is retained as context rather than inferred."""
    records: list[dict[str, Any]] = []
    active_heading, seen_refs, pending = "document", Counter(), []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw.startswith("#"):
            active_heading = raw.lstrip("#").strip()
        match = _MARKDOWN_TABLE.match(raw)
        if not match:
            continue
        cells = [cell.strip() for cell in match.group(1).split("|")]
        if not cells or all(_SEPARATOR.match(cell or "") for cell in cells) or cells[0].lower().startswith(("date", "date seen")):
            continue
        ref = _stable_ref(cells)
        if ref:
            seen_refs[ref] += 1
        pending.append((line_no, cells, active_heading, ref))
    for line_no, cells, heading, ref in pending:
        original = {"heading": heading, "cells": cells, "raw": "| " + " | ".join(cells) + " |"}
        if not ref:
            records.append(_record("seer_expenses_markdown", f"line:{line_no}", "preserved_for_review", reason="no stable source, invoice, receipt, policy, order, or confirmation reference extractable", original=original))
        elif seen_refs[ref] > 1:
            records.append(_record("seer_expenses_markdown", f"line:{line_no}", "preserved_for_review", reason="stable reference repeats in supporting log; retained without deduplication", source_ref=ref, original=original, candidate={"source_ref": f"markdown:reference:{ref}", "proposed_status": "needs_review"}))
        elif f"invoice-{ref}" in known_ledger_refs:
            records.append(_record("seer_expenses_markdown", f"line:{line_no}", "exact_replay", reason="stable invoice reference already occurs in JSON ledger", source_ref=ref, original=original, candidate={"source_ref": f"invoice-{ref}", "proposed_status": "ledger_written"}))
        else:
            records.append(_record("seer_expenses_markdown", f"line:{line_no}", "imported_candidate", source_ref=ref, original=original, candidate={"source_ref": f"markdown:reference:{ref}", "proposed_status": "needs_review"}))
    return records


def parse_queue(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path, "queue")
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return [_record("expense_enrichment_queue", "$.items", "blocked", reason="queue items is not an array", original=data)]
    records = []
    for index, item in enumerate(data["items"]):
        location = f"$.items[{index}]"
        if not isinstance(item, dict):
            records.append(_record("expense_enrichment_queue", location, "blocked", reason="queue item is not an object", original=item)); continue
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            records.append(_record("expense_enrichment_queue", location, "blocked", reason="missing queue source_id", original=item)); continue
        if item.get("state") == "not_needed":
            records.append(_record("expense_enrichment_queue", location, "not_needed", reason="queue item was explicitly rectified/closed as not-needed; retained for audit only", source_ref=source_id, original=item, candidate={"source_ref": source_id, "proposed_status": "not_needed"}))
            continue
        records.append(_record("expense_enrichment_queue", location, "imported_candidate", source_ref=source_id, original=item, candidate={"source_ref": source_id, "source_surface": item.get("source_surface"), "source_excerpt": item.get("source_excerpt"), "evidence_ref": item.get("canonical_ref"), "proposed_status": "needs_review", "reason": "unresolved technical queue item"}))
    return records


def _invoice_key(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.upper().removeprefix("INVOICE-").replace("-", "")
    return value if re.fullmatch(r"INV\d+", value) else None


def parse_tide_reconciliation(path: Path, candidate_refs: set[str]) -> list[dict[str, Any]]:
    """Retain Tide evidence without inferring bank rows or changing candidate state."""
    records: list[dict[str, Any]] = []
    heading, headers = "document", None
    candidate_invoice_refs = {key: ref for ref in candidate_refs if (key := _invoice_key(ref))}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw.startswith("#"):
            heading, headers = raw.lstrip("#").strip(), None
            continue
        table = _MARKDOWN_TABLE.match(raw)
        if table:
            cells = [cell.strip() for cell in table.group(1).split("|")]
            if all(_SEPARATOR.match(cell or "") for cell in cells):
                continue
            if cells and cells[0].lower() == "invoice":
                headers = cells
                continue
            original = {"heading": heading, "cells": cells, "raw": raw}
            if headers and heading == "Incoming payments matched to invoice tracker" and cells and _invoice_key(cells[0]):
                invoice = cells[0]
                matched = candidate_invoice_refs.get(_invoice_key(invoice))
                records.append(_record("tide_reconciliation", f"line:{line_no}", "evidence_supported", reason="exact named invoice receipt table row; evidence only, not an accounting posting", source_ref=invoice, original={**original, "headers": headers}, candidate={"evidence_type": "exact_invoice_receipt", "supports_existing_candidate_ref": matched, "posting_status": "not_posted"}))
            else:
                records.append(_record("tide_reconciliation", f"line:{line_no}", "preserved_for_review", reason="Tide table row retained without individual transaction linkage", original={**original, "headers": headers} if headers else original))
            continue
        rule = _TIDE_RULE.match(raw)
        if rule and heading == "Applied classification tags":
            tag, description = rule.groups()
            records.append(_record("tide_reconciliation", f"line:{line_no}", "confirmed_classification_rule", reason="explicit confirmed Tide classification rule; not applied automatically", source_ref=tag, original={"heading": heading, "raw": raw}, candidate={"evidence_type": "confirmed_classification_rule", "rule": tag, "description": description, "application": "manual_review_required"}))
        elif raw.strip() and not raw.startswith("#") and not _MARKDOWN_TABLE.match(raw):
            records.append(_record("tide_reconciliation", f"line:{line_no}", "preserved_for_review", reason="Tide narrative retained; no individual transaction inferred", original={"heading": heading, "raw": raw}))
    return records


def build_manifest(transactions_path: str | Path, markdown_path: str | Path, queue_path: str | Path, tide_reconciliation_path: str | Path | None = None) -> dict[str, Any]:
    paths = {"transactions_json": Path(transactions_path), "seer_expenses_markdown": Path(markdown_path), "expense_enrichment_queue": Path(queue_path)}
    transaction_records = parse_transactions(paths["transactions_json"])
    known_refs = {r["original_source_ref"] for r in transaction_records if r["original_source_ref"]}
    source_records = {"transactions_json": transaction_records, "seer_expenses_markdown": parse_markdown(paths["seer_expenses_markdown"], known_refs), "expense_enrichment_queue": parse_queue(paths["expense_enrichment_queue"])}
    if tide_reconciliation_path is not None:
        tide_path = Path(tide_reconciliation_path)
        paths["tide_reconciliation"] = tide_path
        candidate_refs = {r["original_source_ref"] for records in source_records.values() for r in records if r["classification"] == "imported_candidate" and r["original_source_ref"]}
        source_records["tide_reconciliation"] = parse_tide_reconciliation(tide_path, candidate_refs)
    all_records = [record for records in source_records.values() for record in records]
    per_source = {source: {"input_items": len(records), "classifications": {state: Counter(r["classification"] for r in records).get(state, 0) for state in sorted(ALLOWED_CLASSIFICATIONS)}} for source, records in source_records.items()}
    totals = Counter(record["classification"] for record in all_records)
    candidates = [r for r in all_records if r["classification"] == "imported_candidate"]
    supported_refs = {r["candidate"].get("supports_existing_candidate_ref") for r in source_records.get("tide_reconciliation", []) if r["classification"] == "evidence_supported" and r.get("candidate", {}).get("supports_existing_candidate_ref")}
    evidence_supported = [r for r in candidates if r.get("original_source_ref") in supported_refs]
    return {"manifest_version": 2, "generated_at": datetime.now(timezone.utc).isoformat(), "mode": "dry_run", "no_write_declaration": "DRY RUN ONLY: this manifest proposes no database, ledger, queue, markdown, runtime, classification application, or accounting posting. Non-dry-run execution is refused.", "tide_evidence_declaration": "When supplied, Tide evidence confirms visible March-July statement reconciliation only. Individual linkage is claimed only for retained exact named invoice receipt table rows.", "backup_requirements": {"status": "handoff_required_later_live_runtime_phase", "scope_boundary": "This Phase 2 dry-run importer creates no SQLite database and implements no backup, scheduler, restore, or health-check runtime.", "requirement": "Every production SQLite instance must be backed up on the same cadence and retention policy as SEER finance code/files.", "snapshot_consistency": "Use SQLite-consistent snapshots (for example SQLite backup API or verified online backup procedure), never an uncoordinated file copy.", "required_manifest": ["backup timestamp", "database checksum", "schema version", "source-watermark", "backup location", "restore-verification result"], "restore_verification": "Each backup policy must include a tested restore verification against an isolated destination.", "health_requirement": "The live runtime health surface must fail closed when the required backup is missed, stale, unverifiable, or restore verification fails."}, "inputs": {name: {"path": str(path), "sha256": _sha256(path)} for name, path in paths.items()}, "per_source": per_source, "summary": {"existing_candidates": len(candidates), "evidence_supported_existing_candidates": len(evidence_supported), "still_manually_reviewable_existing_candidates": len(candidates) - len(evidence_supported), "note": "Evidence support does not change any candidate classification, review status, or accounting posting."}, "totals": {"input_items": len(all_records), "classifications": {state: totals.get(state, 0) for state in sorted(ALLOWED_CLASSIFICATIONS)}}, "records": all_records}

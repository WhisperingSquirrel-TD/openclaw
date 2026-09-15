"""SharePoint-authoritative expense repository.

SQLite's repository remains available for migration and recovery tooling.  This
repository is the business-record boundary used by live SharePoint mode; its
only local state is the read cache and the queue contract.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Mapping

from .expense_repository import (
    Expense,
    ExpenseRepositoryError,
    ExpenseStatus,
    InvalidTransitionError,
    ReceiptEvidence,
    _ALLOWED_TRANSITIONS,
    _validated_facts,
)
from .sharepoint_contract import (
    EXPENSE_LEDGER_PATH,
    SharePointDocumentStore,
    document_content,
    parse_document,
)


class SharePointExpenseRepository:
    """Capture, review, and preserve expense records in one SharePoint document."""

    def __init__(self, *, store: SharePointDocumentStore | None = None, **store_paths: Any) -> None:
        self.store = store or SharePointDocumentStore(**store_paths)

    def close(self) -> None:
        """Match the SQLite repository lifecycle; SharePoint has no open handle."""

    def capture(self, *, source_surface: str, source_ref: str, **facts: Any) -> Expense:
        _require_nonempty(source_surface, "source_surface")
        _require_nonempty(source_ref, "source_ref")
        facts = _validated_facts(facts)
        state = self._read_state()
        existing = next((item for item in state["expenses"] if item["source_ref"] == source_ref), None)
        if existing is None:
            now = _now()
            values = {
                "expense_id": str(uuid.uuid4()),
                "source_surface": source_surface,
                "source_ref": source_ref,
                "status": ExpenseStatus.NEEDS_REVIEW.value,
                "source_timestamp": None,
                "observed_timestamp": now,
                "supplier": None,
                "amount_pence": None,
                "currency": None,
                "expense_date": None,
                "category": None,
                "evidence_ref": None,
                "evidence_state": None,
                "settlement_state": None,
                "finance_ledger_ref": None,
                "validation_result": None,
                "created_at": now,
                "updated_at": now,
            }
            values.update(facts)
            state["expenses"].append(values)
            self._event(state, values["expense_id"], "capture", None,
                        ExpenseStatus.NEEDS_REVIEW.value, "applied", None)
        else:
            conflicts = {
                key: value for key, value in facts.items()
                if value is not None and existing.get(key) is not None and existing.get(key) != value
            }
            if existing["source_surface"] != source_surface:
                conflicts["source_surface"] = source_surface
            if conflicts:
                incoming = {"source_surface": source_surface, **facts}
                collision = {
                    "collision_id": str(uuid.uuid4()),
                    "expense_id": existing["expense_id"],
                    "source_ref": source_ref,
                    "original_facts_json": _canonical_json(_capture_snapshot(existing)),
                    "incoming_facts_json": _canonical_json(incoming),
                    "occurred_at": _now(),
                }
                if not any(
                    item["expense_id"] == existing["expense_id"]
                    and item["incoming_facts_json"] == collision["incoming_facts_json"]
                    for item in state["collisions"]
                ):
                    state["collisions"].append(collision)
            for key, value in facts.items():
                if value is not None and existing.get(key) is None:
                    existing[key] = value
            if conflicts:
                # Ensure an identical collision retry is still a successful
                # readback operation, without appending another event.
                pass
        self._write_state(state, source_ref=source_ref)
        found = next(item for item in state["expenses"] if item["source_ref"] == source_ref)
        return _expense(found)

    def transition(self, expense_id: str, to_status: ExpenseStatus | str) -> Expense:
        try:
            target = ExpenseStatus(to_status)
        except ValueError as exc:
            raise InvalidTransitionError(f"unknown expense status {to_status!r}") from exc
        state = self._read_state()
        row = self._row(state, expense_id)
        current = ExpenseStatus(row["status"])
        if target not in _ALLOWED_TRANSITIONS[current]:
            self._event(state, expense_id, "transition", current.value, target.value,
                        "rejected", "invalid_transition")
            self._write_state(state, source_ref=row["source_ref"])
            raise InvalidTransitionError(f"cannot transition {current.value} to {target.value}")
        row["status"] = target.value
        row["updated_at"] = _now()
        self._event(state, expense_id, "transition", current.value, target.value,
                    "applied", None)
        self._write_state(state, source_ref=row["source_ref"])
        return _expense(row)

    def get(self, expense_id: str) -> Expense:
        return _expense(self._row(self._read_state(), expense_id))

    def finalize_ledger_write(self, expense_id: str, finance_ledger_ref: str) -> Expense:
        _require_nonempty(finance_ledger_ref, "finance_ledger_ref")
        state = self._read_state()
        row = self._row(state, expense_id)
        current = ExpenseStatus(row["status"])
        if current is not ExpenseStatus.LEDGER_READY:
            self._event(state, expense_id, "transition", current.value,
                        ExpenseStatus.LEDGER_WRITTEN.value, "rejected", "invalid_transition")
            self._write_state(state, source_ref=row["source_ref"])
            raise InvalidTransitionError(f"cannot transition {current.value} to ledger_written")
        if row["finance_ledger_ref"] is not None:
            self._event(state, expense_id, "transition", current.value,
                        ExpenseStatus.LEDGER_WRITTEN.value, "rejected",
                        "finance_reference_already_set")
            self._write_state(state, source_ref=row["source_ref"])
            raise ExpenseRepositoryError("finance_ledger_ref is already set")
        if any(item["expense_id"] == expense_id for item in state["collisions"]):
            self._event(state, expense_id, "transition", current.value,
                        ExpenseStatus.LEDGER_WRITTEN.value, "rejected",
                        "capture_collision_unresolved")
            self._write_state(state, source_ref=row["source_ref"])
            raise ExpenseRepositoryError("expense has unresolved capture collisions")
        if any(
            item.get("finance_ledger_ref") == finance_ledger_ref
            and item["expense_id"] != expense_id
            for item in state["expenses"]
        ):
            self._event(state, expense_id, "transition", current.value,
                        ExpenseStatus.LEDGER_WRITTEN.value, "rejected",
                        "finance_reference_conflict")
            self._write_state(state, source_ref=row["source_ref"])
            raise ExpenseRepositoryError("finance_ledger_ref conflicts with another expense")
        row["finance_ledger_ref"] = finance_ledger_ref
        row["status"] = ExpenseStatus.LEDGER_WRITTEN.value
        row["updated_at"] = _now()
        self._event(state, expense_id, "transition", current.value,
                    ExpenseStatus.LEDGER_WRITTEN.value, "applied", None)
        self._write_state(state, source_ref=row["source_ref"])
        return _expense(row)

    def record_receipt_evidence(self, *, source_ref: str, evidence_kind: str,
                                local_path: str | None = None, sha256: str | None = None,
                                sharepoint_path: str | None = None,
                                sharepoint_url: str | None = None,
                                sharepoint_etag: str | None = None,
                                source_timestamp: str | None = None) -> ReceiptEvidence:
        _require_nonempty(source_ref, "source_ref")
        _require_nonempty(evidence_kind, "evidence_kind")
        if sha256 is not None and (
            not isinstance(sha256, str) or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters when supplied")
        state = self._read_state()
        self._find_source(state, source_ref)
        key = (source_ref, evidence_kind, sha256 or "", sharepoint_path or "", sharepoint_etag or "")
        existing = next(
            (
                item for item in state["evidence"]
                if (item["source_ref"], item["evidence_kind"], item.get("sha256") or "",
                    item.get("sharepoint_path") or "", item.get("sharepoint_etag") or "") == key
            ),
            None,
        )
        if existing is None:
            existing = {
                "evidence_id": str(uuid.uuid4()),
                "source_ref": source_ref,
                "evidence_kind": evidence_kind,
                "local_path": local_path,
                "sha256": sha256,
                "sharepoint_path": sharepoint_path,
                "sharepoint_url": sharepoint_url,
                "sharepoint_etag": sharepoint_etag,
                "source_timestamp": source_timestamp,
                "created_at": _now(),
            }
            state["evidence"].append(existing)
            self._write_state(state, source_ref=source_ref)
        return _receipt_evidence(existing)

    def receipt_evidence(self, source_ref: str) -> list[ReceiptEvidence]:
        _require_nonempty(source_ref, "source_ref")
        return [_receipt_evidence(item) for item in self._read_state()["evidence"]
                if item["source_ref"] == source_ref]

    def events(self, expense_id: str) -> list[dict[str, Any]]:
        return [item for item in self._read_state()["events"] if item["expense_id"] == expense_id]

    def capture_collisions(self, expense_id: str) -> list[dict[str, Any]]:
        return [item for item in self._read_state()["collisions"] if item["expense_id"] == expense_id]

    def holding_tray(self) -> list[dict[str, Any]]:
        return [
            dict(item) for item in self._read_state()["expenses"]
            if item["status"] in {"needs_review", "blocked"}
        ]

    def _read_state(self) -> dict[str, Any]:
        content = self.store.read(EXPENSE_LEDGER_PATH)
        value = parse_document(content, path=EXPENSE_LEDGER_PATH)
        if value.get("schema_version") != 1:
            raise ExpenseRepositoryError("invalid SharePoint expense ledger schema")
        for key in ("expenses", "events", "collisions", "evidence"):
            if not isinstance(value.get(key), list):
                raise ExpenseRepositoryError(f"invalid SharePoint expense ledger {key}")
        return value

    def _write_state(self, state: dict[str, Any], *, source_ref: str) -> None:
        self.store.write(
            path=EXPENSE_LEDGER_PATH,
            content=document_content("Expense ledger", state),
            delivery={"kind": "seer_finance_expense", "source_ref": source_ref},
        )

    @staticmethod
    def _row(state: dict[str, Any], expense_id: str) -> dict[str, Any]:
        row = next((item for item in state["expenses"] if item["expense_id"] == expense_id), None)
        if row is None:
            raise ExpenseRepositoryError(f"unknown expense_id {expense_id!r}")
        return row

    @staticmethod
    def _find_source(state: dict[str, Any], source_ref: str) -> dict[str, Any]:
        row = next((item for item in state["expenses"] if item["source_ref"] == source_ref), None)
        if row is None:
            raise ExpenseRepositoryError(f"unknown source_ref {source_ref!r}")
        return row

    @staticmethod
    def _event(state: dict[str, Any], expense_id: str, event_type: str,
               from_status: str | None, to_status: str | None,
               outcome: str, error_code: str | None) -> None:
        state["events"].append({
            "event_id": str(uuid.uuid4()),
            "expense_id": expense_id,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "outcome": outcome,
            "error_code": error_code,
            "occurred_at": _now(),
            "duration_ms": 0,
        })


def _expense(row: Mapping[str, Any]) -> Expense:
    values = dict(row)
    values["status"] = ExpenseStatus(values["status"])
    return Expense(**values)


def _receipt_evidence(row: Mapping[str, Any]) -> ReceiptEvidence:
    return ReceiptEvidence(**dict(row))


def _capture_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in (
        "source_surface", "source_timestamp", "observed_timestamp", "supplier",
        "amount_pence", "currency", "expense_date", "category", "evidence_ref",
        "evidence_state", "settlement_state", "finance_ledger_ref", "validation_result",
    )}


def _canonical_json(values: Mapping[str, Any]) -> str:
    return json.dumps(dict(values), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _require_nonempty(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


SharePointRepository = SharePointExpenseRepository
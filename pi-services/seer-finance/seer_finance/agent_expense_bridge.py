"""Fixed, owner-tool adapter for the canonical SharePoint expense boundary.

This is intentionally a JSON stdin/stdout adapter, not a general command or
SharePoint client. The OpenClaw tool can invoke only three actions: read the
fixed expense workbook, source-linked capture through its typed repository, or
upload one verified inbound-media receipt to a content-addressed filename in an
approved existing Expenses folder. The queue processor remains the only
Graph/remote writer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from seer_finance.sharepoint_boundary import BoundaryResult, SharePointBoundary, get_boundary
from seer_finance.ledger.sharepoint_contract import (
    SharePointMutationBlocked,
    SharePointRebaseRequired,
    SharePointWritePending,
)
from seer_finance.ledger.sharepoint_repository import (
    CaptureCollisionPending,
    SharePointExpenseRepository,
)
from seer_finance.ledger.workbook_codec import WorkbookCodec

EXPENSE_WORKBOOK_PATH = "/Expenses/Expense ledger.xlsx"
APPROVED_RECEIPT_FOLDERS = frozenset({
    "Anthropic", "ChatGPT", "Expenses", "Meals & Refreshments", "Not organised",
    "OpenAI API", "Receipts", "Replit", "SEER",
})
MAX_RECEIPT_BYTES = 50 * 1024 * 1024
_SOURCE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".pdf": "application/pdf",
}
_REQUEST_KEYS = {
    "read_expense_workbook": frozenset({"action", "page", "page_size"}),
    "capture_expense": frozenset({"action", "source_ref", "facts"}),
    "upload_expense_receipt": frozenset({
        "action", "source_ref", "receipt_media_path", "receipt_folder",
    }),
}
_FACT_KEYS = frozenset({
    "source_timestamp", "observed_timestamp", "supplier", "amount_pence",
    "currency", "expense_date", "category", "evidence_ref", "evidence_state",
    "settlement_state", "finance_ledger_ref", "validation_result",
})
DEFAULT_READ_PAGE_SIZE = 25
MAX_READ_PAGE_SIZE = 50


def _result_payload(result: BoundaryResult) -> dict[str, Any]:
    return {
        "operation": result.operation,
        "path": result.path,
        "accepted": result.accepted,
        "verified": result.verified,
        "complete": result.complete,
        "canonical_ref": result.canonical_ref,
        "blocker": result.blocker,
    }


def _state_dir() -> Path:
    return Path(os.environ.get("OPENCLAW_STATE_DIR", Path.home() / ".openclaw"))


def _media_root() -> Path:
    # Test/recovery override remains service-owned configuration, never a tool
    # argument. Production defaults to OpenClaw's inbound-media directory.
    return Path(os.environ.get("SEER_FINANCE_EXPENSE_MEDIA_ROOT", _state_dir() / "media" / "inbound"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as receipt:
        for block in iter(lambda: receipt.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validated_receipt_path(value: Any) -> tuple[Path, str, str]:
    if not isinstance(value, str) or not value:
        raise ValueError("receipt_media_path required")
    supplied = Path(value)
    root = _media_root().resolve()
    if supplied.is_symlink():
        raise ValueError("receipt_media_path must not be a symlink")
    try:
        candidate = supplied.resolve(strict=True)
    except OSError as exc:
        raise ValueError("receipt_media_path is not an available inbound media file") from exc
    if root != candidate.parent and root not in candidate.parents:
        raise ValueError("receipt_media_path must be an OpenClaw inbound media file")
    if not candidate.is_file():
        raise ValueError("receipt_media_path must be a regular inbound media file")
    size = candidate.stat().st_size
    if size <= 0 or size > MAX_RECEIPT_BYTES:
        raise ValueError("receipt media must be between 1 byte and 50 MB")
    mime_type = _MIME_BY_SUFFIX.get(candidate.suffix.lower())
    if mime_type is None:
        raise ValueError("inbound receipt file extension is not supported")
    return candidate, _sha256_file(candidate), mime_type


def _required_string(request: Mapping[str, Any], name: str) -> str:
    value = request.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} required")
    return value


def _validate_request_shape(request: Mapping[str, Any], action: Any) -> str:
    if not isinstance(action, str) or action not in _REQUEST_KEYS:
        raise ValueError("action is not an approved expense operation")
    unexpected = set(request) - _REQUEST_KEYS[action]
    if unexpected:
        raise ValueError(f"request has unsupported field(s): {sorted(unexpected)}")
    return action


def _upload_receipt(request: Mapping[str, Any], boundary: SharePointBoundary) -> dict[str, Any]:
    source_ref = _required_string(request, "source_ref")
    receipt_folder = _required_string(request, "receipt_folder")
    if not _SOURCE_REF.fullmatch(source_ref):
        raise ValueError("source_ref contains unsupported characters")
    if receipt_folder not in APPROVED_RECEIPT_FOLDERS:
        raise ValueError("receipt_folder must be one approved existing Expenses folder")
    local_path, content_sha256, mime_type = _validated_receipt_path(request.get("receipt_media_path"))
    sharepoint_path = (
        f"/Expenses/{content_sha256}{local_path.suffix.lower()}"
        if receipt_folder == "Expenses"
        else f"/Expenses/{receipt_folder}/{content_sha256}{local_path.suffix.lower()}"
    )
    result = boundary.upload_receipt_verified(
        path=sharepoint_path,
        source_ref=source_ref,
        local_path=str(local_path),
        content_sha256=content_sha256,
        mime_type=mime_type,
    )
    return {"ok": result.accepted, "result": _result_payload(result)}


def _expense_payload(expense: Any) -> dict[str, Any]:
    """Return the visible canonical row, never local paths or service state."""
    return {
        name: getattr(expense, name)
        for name in (
            "expense_id", "source_surface", "source_ref", "status", "source_timestamp",
            "observed_timestamp", "supplier", "amount_pence", "currency", "expense_date",
            "category", "evidence_ref", "evidence_state", "settlement_state",
            "finance_ledger_ref", "validation_result",
        )
    }


def _capture_result(*, accepted: bool, verified: bool, blocker: str | None = None,
                    expense: Any | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "operation": "capture_expense",
        "path": EXPENSE_WORKBOOK_PATH,
        "accepted": accepted,
        "verified": verified,
        "complete": accepted and verified,
    }
    if blocker:
        result["blocker"] = blocker
    if expense is not None:
        result["expense"] = _expense_payload(expense)
    return {"ok": accepted, "result": result}


def _matches_incoming_facts(expense: Any, facts: Mapping[str, Any]) -> bool:
    return all(getattr(expense, field, None) == value for field, value in facts.items())


def _capture_expense(
    request: Mapping[str, Any],
    repository: SharePointExpenseRepository | None = None,
) -> dict[str, Any]:
    source_ref = _required_string(request, "source_ref")
    facts = request.get("facts")
    if not _SOURCE_REF.fullmatch(source_ref):
        raise ValueError("source_ref contains unsupported characters")
    if not isinstance(facts, Mapping):
        raise ValueError("facts must be an object of supported expense fields")
    unknown_facts = set(facts) - _FACT_KEYS
    if unknown_facts:
        raise ValueError(f"unknown expense fact(s): {sorted(unknown_facts)}")
    # The repository owns the visible-table merge and validates its small,
    # source-linked fact schema. The tool cannot specify another source
    # surface, workbook, queue, or remote destination.
    try:
        expense = (repository or SharePointExpenseRepository()).capture(
            source_surface="owner_chat",
            source_ref=source_ref,
            **dict(facts),
        )
    except (CaptureCollisionPending, SharePointMutationBlocked, SharePointRebaseRequired) as exc:
        return _capture_result(accepted=False, verified=False, blocker=str(exc))
    except SharePointWritePending as exc:
        return _capture_result(accepted=True, verified=False, blocker=str(exc))
    active_repository = repository or SharePointExpenseRepository()
    collisions = active_repository.capture_collisions(expense.expense_id)
    if collisions:
        return _capture_result(
            accepted=False,
            verified=True,
            blocker="expense has unresolved capture collisions",
            expense=expense,
        )
    if not _matches_incoming_facts(expense, facts):
        return _capture_result(
            accepted=False,
            verified=True,
            blocker="verified expense readback does not match incoming facts",
            expense=expense,
        )
    return _capture_result(accepted=True, verified=True, expense=expense)


def _page_value(request: Mapping[str, Any], name: str, *, minimum: int, maximum: int,
                default: int) -> int:
    value = request.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _public_expense_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "expense_id", "source_surface", "source_ref", "status", "source_timestamp",
            "observed_timestamp", "supplier", "amount_pence", "currency", "expense_date",
            "category", "evidence_ref", "evidence_state", "settlement_state",
            "finance_ledger_ref", "validation_result", "created_at", "updated_at",
        )
    }


def _read_expense_workbook(
    request: Mapping[str, Any], boundary: SharePointBoundary
) -> dict[str, Any]:
    page = _page_value(request, "page", minimum=0, maximum=10_000, default=0)
    page_size = _page_value(
        request, "page_size", minimum=1, maximum=MAX_READ_PAGE_SIZE,
        default=DEFAULT_READ_PAGE_SIZE,
    )
    snapshot = boundary.read_workbook_snapshot(EXPENSE_WORKBOOK_PATH)
    raw_content = snapshot.get("content_bytes")
    if not isinstance(raw_content, bytes):
        raise ValueError("authenticated workbook snapshot lacks canonical binary content")
    state = WorkbookCodec.decode_expense(raw_content)
    expenses = state.get("expenses")
    evidence = state.get("evidence")
    events = state.get("events")
    if not isinstance(expenses, list) or not isinstance(evidence, list) or not isinstance(events, list):
        raise ValueError("canonical expense workbook has an invalid visible table")
    start = page * page_size
    selected = [row for row in expenses[start:start + page_size] if isinstance(row, Mapping)]
    source_refs = {row.get("source_ref") for row in selected}
    expense_ids = {row.get("expense_id") for row in selected}
    # Keep every returned collection bounded and avoid exposing local evidence
    # paths. The visible rows carry the canonical status and evidence_ref.
    public_evidence = [
        {
            key: item.get(key)
            for key in (
                "evidence_id", "source_ref", "evidence_kind", "sha256",
                "sharepoint_path", "sharepoint_url", "sharepoint_etag",
                "source_timestamp", "created_at",
            )
        }
        for item in evidence
        if isinstance(item, Mapping) and item.get("source_ref") in source_refs
    ][:MAX_READ_PAGE_SIZE]
    public_events = [
        {
            key: item.get(key)
            for key in (
                "event_id", "expense_id", "event_type", "from_status", "to_status",
                "outcome", "error_code", "occurred_at",
            )
        }
        for item in events
        if isinstance(item, Mapping) and item.get("expense_id") in expense_ids
    ][:MAX_READ_PAGE_SIZE]
    total = len(expenses)
    return {
        "ok": True,
        "metadata": {
            "path": EXPENSE_WORKBOOK_PATH,
            "etag": snapshot.get("etag"),
            "version": snapshot.get("version"),
            "synced_at": snapshot.get("synced_at"),
            "content_sha256": snapshot.get("content_sha256"),
            "semantic_workbook_sha256": snapshot.get("semantic_workbook_sha256"),
            "schema_version": state.get("schema_version"),
            "total_expenses": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "approved_receipt_folders": sorted(APPROVED_RECEIPT_FOLDERS),
        },
        "rows": [_public_expense_row(row) for row in selected],
        "evidence": public_evidence,
        "status_events": public_events,
    }


def handle(
    request: Mapping[str, Any],
    *,
    boundary: SharePointBoundary | None = None,
    repository: SharePointExpenseRepository | None = None,
) -> dict[str, Any]:
    """Execute one allowlisted operation and return a redacted JSON response."""
    try:
        if not isinstance(request, Mapping):
            raise ValueError("request must be an object")
        action = _validate_request_shape(request, request.get("action"))
        if action == "read_expense_workbook":
            service = boundary or get_boundary()
            return _read_expense_workbook(request, service)
        if action == "capture_expense":
            return _capture_expense(request, repository)
        if action == "upload_expense_receipt":
            service = boundary or get_boundary()
            return _upload_receipt(request, service)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:500]}


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"ok": False, "error": "request must be valid JSON"}))
        return 0
    print(json.dumps(handle(request), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
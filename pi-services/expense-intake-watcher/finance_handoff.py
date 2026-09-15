"""SharePoint-authoritative finance handoff.

This module is intentionally not a file-backed ledger writer.  The watcher may
prepare a source-linked candidate, but only the public seer-finance boundary
may capture, review, post, or claim completion for it.  Local JSON queues and
outcome state are recovery state and are never consulted as business truth.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from sharepoint_boundary import (
    BoundaryResult,
    FINANCE_LEDGER_PATH,
    SharePointBoundary,
    SharePointBoundaryError,
)


class TransactionValidationError(ValueError):
    """Candidate facts are incomplete or unsafe for finance handoff."""


_REQUIRED_FIELDS = (
    "date",
    "direction",
    "amount_pence",
    "description",
    "counterparty",
    "category",
    "source_ref",
)


def _validate_candidate(candidate: Mapping[str, Any]) -> None:
    missing = [field for field in _REQUIRED_FIELDS if candidate.get(field) in (None, "")]
    if missing:
        raise TransactionValidationError(
            f"finance handoff requires complete candidate fields: {', '.join(missing)}"
        )
    if candidate.get("direction") != "expense":
        raise TransactionValidationError("finance handoff accepts expense candidates only")
    amount = candidate.get("amount_pence")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise TransactionValidationError("amount_pence must be a non-negative integer")


def update_validated_expense(
    boundary: SharePointBoundary,
    candidate: Mapping[str, Any],
) -> BoundaryResult:
    """Offer one complete expense to ``/Finance/Finance ledger.xlsx``.

    The boundary owns validation against the existing document, source-ref
    idempotency, table-preserving workbook update, and verified readback. We
    deliberately do not accept a local path argument: a local transactions
    file cannot be the business authority after cutover.
    """
    _validate_candidate(candidate)
    source_ref = str(candidate["source_ref"])
    # Enrichment workers are allowed to provide accounting facts without
    # inventing a second identity.  Derive a stable transaction id from the
    # already-required source reference; retries then address the same visible
    # workbook row instead of failing validation or creating duplicates.
    normalized = dict(candidate)
    if normalized.get("txn_id") in (None, ""):
        normalized["txn_id"] = (
            "expense-" + hashlib.sha256(source_ref.encode("utf-8")).hexdigest()[:24]
        )
    public_handoff = getattr(boundary, "update_validated_expense", None)
    if callable(public_handoff):
        result = public_handoff(normalized)
        if not isinstance(result, BoundaryResult):
            raise SharePointBoundaryError("seer-finance finance handoff returned an invalid result")
        return result
    return BoundaryResult(
        operation="update_workbook",
        path=FINANCE_LEDGER_PATH,
        accepted=False,
        verified=False,
        blocker=(
            "seer-finance structured finance workbook boundary is unavailable "
            f"for source_ref {source_ref}"
        ),
    )

def capture_review_expense(
    boundary: SharePointBoundary,
    *,
    source_surface: str,
    source_ref: str,
    facts: Mapping[str, Any] | None = None,
) -> BoundaryResult:
    """Delegate capture/review preparation to seer-finance's public boundary."""
    method = getattr(boundary, "capture_candidate", None)
    if not callable(method):
        raise SharePointBoundaryError(
            "seer-finance boundary does not expose capture_candidate"
        )
    result = method(
        source_surface=source_surface,
        source_ref=source_ref,
        facts=dict(facts or {}),
    )
    if not isinstance(result, BoundaryResult):
        raise SharePointBoundaryError("seer-finance capture returned an invalid result")
    return result
"""SharePoint-authoritative finance handoff.

This module is intentionally not a file-backed ledger writer.  The watcher may
prepare a source-linked candidate, but only the public seer-finance boundary
may capture, review, post, or claim completion for it.  Local JSON queues and
outcome state are recovery state and are never consulted as business truth.
"""
from __future__ import annotations

from typing import Any, Mapping

from sharepoint_boundary import (
    BoundaryResult,
    FINANCE_LEDGER_PATH,
    SharePointBoundary,
    SharePointBoundaryError,
    write_verified,
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


def append_validated_expense(
    boundary: SharePointBoundary,
    candidate: Mapping[str, Any],
) -> BoundaryResult:
    """Offer one complete expense to ``/Finance/Finance ledger.md``.

    The boundary owns validation against the existing document, source-ref
    idempotency, bounded write policy, and verified readback.  We deliberately
    do not accept a local path argument: a local transactions file cannot be
    the business authority after cutover.
    """
    _validate_candidate(candidate)
    source_ref = str(candidate["source_ref"])
    public_handoff = getattr(boundary, "append_validated_expense", None)
    if callable(public_handoff):
        result = public_handoff(dict(candidate))
        if not isinstance(result, BoundaryResult):
            raise SharePointBoundaryError("seer-finance finance handoff returned an invalid result")
        return result
    # The public boundary accepts structured JSON content so that it can apply
    # its own schema and append/idempotency rules without the watcher parsing
    # or rewriting a finance document.
    import json

    content = json.dumps(
        {"kind": "expense_handoff", "source_ref": source_ref, "candidate": dict(candidate)},
        sort_keys=True,
    )
    result = write_verified(
        FINANCE_LEDGER_PATH,
        content,
        operation="append",
        boundary=boundary,
    )
    if result.complete and not result.canonical_ref:
        return BoundaryResult(
            operation=result.operation,
            path=result.path,
            accepted=result.accepted,
            verified=result.verified,
            canonical_ref=f"{FINANCE_LEDGER_PATH}#source_ref:{source_ref}",
            content=result.content,
            blocker=result.blocker,
        )
    return result


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
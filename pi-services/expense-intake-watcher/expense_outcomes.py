"""Deterministic expense-intake outcome contract.

This module is deliberately free of mailbox, filesystem and finance-engine access so
all source adapters can be tested against the same fail-closed contract.  The
runtime owner is responsible for persisting the returned record to the canonical
expense log, finance ledger/evidence queues and health surface.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal

ExpenseOutcome = Literal["logged", "duplicate", "blocked", "not_needed"]
LedgerState = Literal["not_required", "pending", "written", "blocked"]
EvidenceState = Literal["not_required", "pending", "retained", "blocked"]

_ALLOWED_OUTCOMES = {"logged", "duplicate", "blocked", "not_needed"}
_ALLOWED_LEDGER = {"not_required", "pending", "written", "blocked"}
_ALLOWED_EVIDENCE = {"not_required", "pending", "retained", "blocked"}


@dataclass(frozen=True)
class ExpenseOutcomeRecord:
    source_id: str
    source_surface: str
    observed_at: str
    expense_outcome: ExpenseOutcome
    canonical_ref: str | None
    ledger_state: LedgerState
    evidence_state: EvidenceState
    blocker: str | None = None
    candidate_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_outcome(
    *,
    source_id: str,
    source_surface: str,
    expense_outcome: ExpenseOutcome,
    canonical_ref: str | None,
    ledger_state: LedgerState,
    evidence_state: EvidenceState,
    blocker: str | None = None,
    candidate_reason: str | None = None,
    observed_at: str | None = None,
) -> ExpenseOutcomeRecord:
    """Create one valid, auditable outcome or fail closed.

    A source event cannot be reported complete from a loose supplier/string
    match.  A durable canonical reference is mandatory for logged/duplicate
    results.  A blocked result carries the exact blocker; not-needed is the
    only terminal result that deliberately has no expense record.
    """
    if not source_id or not source_surface:
        raise ValueError("source_id and source_surface are required")
    if expense_outcome not in _ALLOWED_OUTCOMES:
        raise ValueError(f"unsupported expense outcome: {expense_outcome}")
    if ledger_state not in _ALLOWED_LEDGER or evidence_state not in _ALLOWED_EVIDENCE:
        raise ValueError("unsupported ledger/evidence state")
    if expense_outcome in {"logged", "duplicate"} and not canonical_ref:
        raise ValueError("logged/duplicate outcome requires exact canonical_ref")
    if expense_outcome == "blocked" and not blocker:
        raise ValueError("blocked outcome requires exact blocker")
    if expense_outcome == "not_needed" and canonical_ref:
        raise ValueError("not_needed outcome cannot claim canonical expense completion")
    if expense_outcome in {"logged", "duplicate"} and ledger_state == "blocked":
        raise ValueError("logged/duplicate outcome cannot hide blocked ledger state")
    return ExpenseOutcomeRecord(
        source_id=source_id,
        source_surface=source_surface,
        observed_at=observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        expense_outcome=expense_outcome,
        canonical_ref=canonical_ref,
        ledger_state=ledger_state,
        evidence_state=evidence_state,
        blocker=blocker,
        candidate_reason=candidate_reason,
    )

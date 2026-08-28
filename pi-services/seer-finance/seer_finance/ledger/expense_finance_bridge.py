"""Explicit, non-live bridge from reviewed expenses to an injected finance writer.

This module deliberately has no transaction-file path and no default writer.
A caller must provide the existing finance writer/validator boundary explicitly.
It builds no financial facts: every accounting field arrives in the proposed
transaction and is strictly validated by the existing transaction loader.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from .expense_repository import Expense, ExpenseRepository, ExpenseRepositoryError, ExpenseStatus
from .loader import TransactionValidationError, parse_transaction
from .schema import Transaction

logger = logging.getLogger(__name__)


class FinanceWriter(Protocol):
    """Existing ledger boundary supplied by the explicit caller, never constructed here."""

    def validate_and_write(self, transaction: Transaction) -> str:
        """Validate/write once and return its immutable finance-ledger reference."""


class FinanceWriterRejected(RuntimeError):
    """A writer refused a transaction without writing it."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class FinanceReferenceConflict(FinanceWriterRejected):
    """The writer reports an existing or conflicting accounting/source reference."""

    def __init__(self, message: str = "finance reference conflicts with an existing transaction") -> None:
        super().__init__("finance_reference_conflict", message)


class FinancePostOutcome(str, Enum):
    POSTED = "posted"
    REFUSED = "refused"
    BLOCKED = "blocked"
    ALREADY_POSTED = "already_posted"


@dataclass(frozen=True)
class FinancePostResult:
    outcome: FinancePostOutcome
    expense_id: str
    status: ExpenseStatus
    error_code: str | None = None
    finance_ledger_ref: str | None = None
    proposed_transaction: Mapping[str, Any] | None = None

    def log_fields(self) -> dict[str, Any]:
        """Stable structured fields for callers which emit operational logs."""
        return asdict(self)


class ExpenseFinanceBridge:
    """One explicit posting attempt against a supplied repository and writer."""

    def __init__(self, repository: ExpenseRepository, writer: FinanceWriter) -> None:
        self._repository = repository
        self._writer = writer

    def post(self, expense_id: str, proposed_transaction: Mapping[str, Any]) -> FinancePostResult:
        """Validate then offer a canonical expense transaction to the injected writer.

        A refusal or writer rejection never changes the expense status or its
        retained evidence.  Only a successful writer response reaches the
        repository's atomic reference-plus-transition operation.
        """
        started = time.monotonic()
        expense = self._repository.get(expense_id)
        if expense.status is ExpenseStatus.LEDGER_WRITTEN:
            return self._result(FinancePostOutcome.ALREADY_POSTED, expense,
                                finance_ledger_ref=expense.finance_ledger_ref,
                                started=started)
        if expense.status is not ExpenseStatus.LEDGER_READY:
            return self._result(FinancePostOutcome.REFUSED, expense,
                                error_code="expense_not_ledger_ready", started=started)
        if expense.finance_ledger_ref is not None:
            return self._result(FinancePostOutcome.BLOCKED, expense,
                                error_code="finance_reference_already_set", started=started)
        if self._repository.capture_collisions(expense_id):
            return self._result(FinancePostOutcome.BLOCKED, expense,
                                error_code="capture_collision_unresolved", started=started)

        canonical, validation_error = _canonical_transaction(expense, proposed_transaction)
        if validation_error is not None:
            return self._result(FinancePostOutcome.REFUSED, expense,
                                error_code=validation_error, started=started)
        assert canonical is not None
        try:
            transaction = parse_transaction(canonical, 0)
        except TransactionValidationError:
            # This should be unreachable after canonical validation, but it
            # keeps the existing strict type boundary authoritative.
            return self._result(FinancePostOutcome.REFUSED, expense,
                                error_code="transaction_schema_invalid",
                                proposed_transaction=canonical, started=started)
        try:
            finance_ref = self._writer.validate_and_write(transaction)
            if not isinstance(finance_ref, str) or not finance_ref.strip():
                raise FinanceWriterRejected("writer_invalid_finance_reference",
                                            "writer returned an empty finance reference")
        except FinanceWriterRejected as exc:
            return self._result(FinancePostOutcome.BLOCKED, expense,
                                error_code=exc.error_code,
                                proposed_transaction=canonical, started=started)
        except Exception:
            logger.exception("expense_finance_bridge writer_failure expense_id=%s source_ref=%s",
                             expense.expense_id, expense.source_ref)
            return self._result(FinancePostOutcome.BLOCKED, expense,
                                error_code="writer_rejected",
                                proposed_transaction=canonical, started=started)

        try:
            written = self._repository.finalize_ledger_write(expense_id, finance_ref)
        except ExpenseRepositoryError as exc:
            # Writer success is not silently retried. The local record remains
            # visible for reconciliation and the caller receives a hard block.
            return self._result(FinancePostOutcome.BLOCKED, self._repository.get(expense_id),
                                error_code=_repository_error_code(exc),
                                proposed_transaction=canonical, started=started)
        return self._result(FinancePostOutcome.POSTED, written,
                            finance_ledger_ref=finance_ref,
                            proposed_transaction=canonical, started=started)

    @staticmethod
    def _result(outcome: FinancePostOutcome, expense: Expense, *, started: float,
                error_code: str | None = None, finance_ledger_ref: str | None = None,
                proposed_transaction: Mapping[str, Any] | None = None) -> FinancePostResult:
        result = FinancePostResult(outcome, expense.expense_id, expense.status, error_code,
                                   finance_ledger_ref, proposed_transaction)
        log = logger.warning if outcome in (FinancePostOutcome.REFUSED, FinancePostOutcome.BLOCKED) else logger.info
        log("expense_finance_bridge outcome=%s expense_id=%s source_ref=%s status=%s "
            "error_code=%s finance_ledger_ref=%s duration_ms=%d",
            outcome.value, expense.expense_id, expense.source_ref, expense.status.value,
            error_code, finance_ledger_ref, int((time.monotonic() - started) * 1000))
        return result


def _canonical_transaction(expense: Expense, proposed: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Accept only an exact, complete accounting proposal; derive nothing."""
    if not isinstance(proposed, Mapping):
        return None, "proposed_transaction_not_mapping"
    required = {"txn_id", "date", "direction", "amount_pence", "description", "counterparty", "category"}
    allowed = required | {"pre_trading", "tax_treatment", "source_ref"}
    keys = set(proposed)
    if keys - allowed:
        return None, "transaction_schema_invalid"
    if required - keys:
        return None, "transaction_schema_incomplete"
    # These comparisons bind the supplied accounting entry to this exact
    # expense without transforming values (e.g. no pounds-to-pence conversion).
    if proposed["direction"] != "expense":
        return None, "transaction_direction_mismatch"
    if proposed["amount_pence"] != expense.amount_pence:
        return None, "transaction_amount_mismatch"
    if proposed["date"] != expense.expense_date:
        return None, "transaction_date_mismatch"
    if proposed["counterparty"] != expense.supplier:
        return None, "transaction_counterparty_mismatch"
    if proposed["category"] != expense.category:
        return None, "transaction_category_mismatch"
    if proposed.get("source_ref") != expense.source_ref:
        return None, "transaction_source_ref_mismatch"
    # Stable key order gives writers/logging a canonical plain-data proposal.
    return {key: proposed[key] for key in (
        "txn_id", "date", "direction", "amount_pence", "description", "counterparty",
        "category", "pre_trading", "tax_treatment", "source_ref"
    ) if key in proposed}, None


def _repository_error_code(error: ExpenseRepositoryError) -> str:
    text = str(error)
    if "collision" in text:
        return "capture_collision_unresolved"
    if "already set" in text:
        return "finance_reference_already_set"
    if "conflicts" in text:
        return "finance_reference_conflict"
    return "repository_finalize_failed"

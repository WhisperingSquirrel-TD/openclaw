"""Authoritative SharePoint finance ledger writer."""

from __future__ import annotations

import json
from typing import Any

from .expense_finance_bridge import FinanceReferenceConflict
from .loader import TransactionValidationError, parse_transaction
from .schema import Transaction
from .sharepoint_contract import (
    FINANCE_LEDGER_PATH,
    SharePointDocumentStore,
    SharePointContractError,
    document_content,
    parse_document,
)


class SharePointFinanceWriter:
    """Write reviewed transactions through Pi's SharePoint queue only."""

    def __init__(self, *, store: SharePointDocumentStore | None = None, **store_paths: Any) -> None:
        self.store = store or SharePointDocumentStore(**store_paths)

    def validate_and_write(self, transaction: Transaction) -> str:
        raw = {
            "txn_id": transaction.txn_id,
            "date": transaction.date,
            "direction": transaction.direction.value,
            "amount_pence": transaction.amount_pence,
            "description": transaction.description,
            "counterparty": transaction.counterparty,
            "category": transaction.category.value,
            "pre_trading": transaction.pre_trading,
            "tax_treatment": transaction.tax_treatment.value if transaction.tax_treatment else None,
            "source_ref": transaction.source_ref,
        }
        try:
            checked = parse_transaction(raw, 0)
        except TransactionValidationError as exc:
            raise ValueError(str(exc)) from exc
        payload = _transaction_payload(checked)
        current = self._read_ledger()
        for existing in current["transactions"]:
            if existing.get("source_ref") != checked.source_ref:
                continue
            if existing == payload:
                return f"sharepoint:{existing['txn_id']}"
            raise FinanceReferenceConflict("source_ref already exists with different accounting facts")
        current["transactions"].append(payload)
        content = document_content("Finance ledger", current)
        try:
            self.store.write(
                path=FINANCE_LEDGER_PATH,
                content=content,
                delivery={"kind": "seer_finance_transaction", "source_ref": checked.source_ref},
            )
        except SharePointContractError:
            raise
        return f"sharepoint:{checked.txn_id}"

    def _read_ledger(self) -> dict[str, Any]:
        content = self.store.read(FINANCE_LEDGER_PATH)
        value = parse_document(content, path=FINANCE_LEDGER_PATH)
        transactions = value.get("transactions")
        if value.get("schema_version") != 1 or not isinstance(transactions, list):
            raise ValueError("invalid SharePoint finance ledger document")
        return {"schema_version": 1, "transactions": transactions}


def _transaction_payload(transaction: Transaction) -> dict[str, Any]:
    return {
        "txn_id": transaction.txn_id,
        "date": transaction.date,
        "direction": transaction.direction.value,
        "amount_pence": transaction.amount_pence,
        "description": transaction.description,
        "counterparty": transaction.counterparty,
        "category": transaction.category.value,
        "pre_trading": transaction.pre_trading,
        "tax_treatment": transaction.tax_treatment.value if transaction.tax_treatment else None,
        "source_ref": transaction.source_ref,
    }


SharePointWriter = SharePointFinanceWriter
"""Read the authoritative finance ledger from the SharePoint content cache."""

from __future__ import annotations

from typing import Any

from .loader import TransactionValidationError, parse_transaction
from .schema import Transaction
from .sharepoint_contract import (
    FINANCE_LEDGER_PATH,
    SharePointDocumentStore,
    SharePointContractError,
    parse_document,
)


class SharePointLedgerLoadError(ValueError):
    """The cached authoritative SharePoint finance ledger is unavailable."""


def load_finance_transactions_from_sharepoint(
    *, store: SharePointDocumentStore | None = None, **store_paths: Any
) -> list[Transaction]:
    """Load strictly validated transactions; no Graph access is fabricated here."""
    document_store = store or SharePointDocumentStore(**store_paths)
    try:
        content = document_store.read(FINANCE_LEDGER_PATH)
        if content is None:
            raise SharePointLedgerLoadError(
                "authoritative SharePoint finance ledger is not present in the local cache"
            )
        value = parse_document(content, path=FINANCE_LEDGER_PATH)
        if value.get("schema_version") != 1 or not isinstance(value.get("transactions"), list):
            raise SharePointLedgerLoadError("invalid authoritative SharePoint finance ledger")
        transactions: list[Transaction] = []
        for index, raw in enumerate(value["transactions"]):
            try:
                if not isinstance(raw, dict):
                    raise TransactionValidationError("transaction must be an object")
                transactions.append(parse_transaction(raw, index))
            except TransactionValidationError as exc:
                raise SharePointLedgerLoadError(f"invalid finance transaction at {index}: {exc}") from exc
        return transactions
    except SharePointContractError as exc:
        raise SharePointLedgerLoadError(str(exc)) from exc


# A short alias keeps loader consumers independent of the transport wording.
load_sharepoint_finance_transactions = load_finance_transactions_from_sharepoint
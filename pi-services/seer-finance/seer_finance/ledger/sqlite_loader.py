"""Read canonical accounting transactions from the SQLite finance ledger."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .loader import TransactionValidationError, parse_transaction
from .schema import Transaction


class SqliteLedgerLoadError(ValueError):
    pass


def load_finance_transactions(database: str | Path) -> list[Transaction]:
    """Read immutable finance rows once, deterministically by source reference."""
    try:
        with sqlite3.connect(f"file:{Path(database)}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT source_ref, transaction_json FROM finance_transactions ORDER BY source_ref"
            ).fetchall()
    except sqlite3.Error as exc:
        raise SqliteLedgerLoadError(f"cannot read finance_transactions: {exc}") from exc

    transactions: list[Transaction] = []
    for index, (source_ref, payload) in enumerate(rows):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("source_ref") != source_ref:
                raise SqliteLedgerLoadError(f"invalid immutable transaction payload for {source_ref!r}")
            transactions.append(parse_transaction(raw, index))
        except (json.JSONDecodeError, TransactionValidationError) as exc:
            raise SqliteLedgerLoadError(f"invalid finance transaction {source_ref!r}: {exc}") from exc
    return transactions

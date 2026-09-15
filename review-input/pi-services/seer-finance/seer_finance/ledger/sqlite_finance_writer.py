"""Canonical SQLite accounting writer for reviewed SEER expense transactions."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .expense_finance_bridge import FinanceReferenceConflict
from .schema import Transaction


class SqliteFinanceWriter:
    """Stores a strict transaction once in the operational SQLite database."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self._migrate()

    def _connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database)

    def _migrate(self) -> None:
        with self._connection() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS finance_transactions (
                txn_id TEXT PRIMARY KEY,
                source_ref TEXT NOT NULL UNIQUE,
                transaction_json TEXT NOT NULL,
                written_at TEXT NOT NULL
            )''')

    def validate_and_write(self, transaction: Transaction) -> str:
        payload = json.dumps({
            'txn_id': transaction.txn_id, 'date': transaction.date,
            'direction': transaction.direction.value, 'amount_pence': transaction.amount_pence,
            'description': transaction.description, 'counterparty': transaction.counterparty,
            'category': transaction.category.value, 'pre_trading': transaction.pre_trading,
            'tax_treatment': transaction.tax_treatment.value if transaction.tax_treatment else None,
            'source_ref': transaction.source_ref,
        }, sort_keys=True, separators=(',', ':'))
        ref = f'sqlite:{transaction.txn_id}'
        with self._connection() as con:
            prior = con.execute('SELECT txn_id, transaction_json FROM finance_transactions WHERE source_ref = ?', (transaction.source_ref,)).fetchone()
            if prior:
                if prior[1] == payload:
                    return f'sqlite:{prior[0]}'
                raise FinanceReferenceConflict('source_ref already exists with different accounting facts')
            try:
                con.execute('INSERT INTO finance_transactions (txn_id, source_ref, transaction_json, written_at) VALUES (?, ?, ?, ?)',
                            (transaction.txn_id, transaction.source_ref, payload, datetime.now(timezone.utc).isoformat()))
            except sqlite3.IntegrityError as exc:
                raise FinanceReferenceConflict(str(exc)) from exc
        return ref

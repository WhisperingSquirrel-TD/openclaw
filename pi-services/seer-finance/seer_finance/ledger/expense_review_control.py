"""Controlled SQLite review and finance-posting boundary for SEER expenses.

This is intentionally a local authenticated/control-plane primitive, not a
free-form importer: it acts only on an existing SQLite expense ID and always
preserves source evidence/audit events through ExpenseRepository.
"""
from __future__ import annotations
import os

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .expense_finance_bridge import ExpenseFinanceBridge, FinancePostResult
from .expense_repository import ExpenseRepository, ExpenseStatus
from .sqlite_finance_writer import SqliteFinanceWriter

DEFAULT_DATABASE = Path(os.environ.get('SEER_FINANCE_DATABASE', '/var/lib/seer-finance/expense-ledger.sqlite3'))
_REQUIRED_CONFIRMATION_FIELDS = ('supplier', 'amount_pence', 'currency', 'expense_date', 'category', 'evidence_ref', 'evidence_state', 'settlement_state')


def list_holding_tray(database: str | Path = DEFAULT_DATABASE) -> list[dict[str, Any]]:
    repo = ExpenseRepository(database)
    try:
        rows = repo.connection.execute(
            "SELECT * FROM expenses WHERE status IN ('needs_review','blocked') ORDER BY observed_timestamp, expense_id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        repo.close()


def review_expense(*, expense_id: str, decision: str, facts: Mapping[str, Any] | None = None,
                   database: str | Path = DEFAULT_DATABASE) -> dict[str, Any]:
    """Apply an explicit review decision without inventing values.

    ``confirm`` admits only a fully evidenced expense and marks it ledger-ready;
    ``not_business`` and ``duplicate`` remove a reviewed item from the working
    tray but retain the original source and events.  No decision posts finance.
    """
    if decision not in {'confirm', 'not_business', 'duplicate'}:
        raise ValueError('decision must be confirm, not_business or duplicate')
    repo = ExpenseRepository(database)
    try:
        current = repo.get(expense_id)
        if current.status is not ExpenseStatus.NEEDS_REVIEW:
            raise ValueError(f'expense is not reviewable from status {current.status.value}')
        if facts:
            enriched = repo.capture(source_surface=current.source_surface, source_ref=current.source_ref, **dict(facts))
            if repo.capture_collisions(expense_id):
                raise ValueError('review refused: conflicting source facts are retained for resolution')
            current = enriched
        if decision == 'confirm':
            missing = [field for field in _REQUIRED_CONFIRMATION_FIELDS if getattr(current, field) in (None, '')]
            if missing:
                raise ValueError(f'review refused: confirmation lacks {", ".join(missing)}')
            current = repo.transition(expense_id, ExpenseStatus.CONFIRMED)
            current = repo.transition(expense_id, ExpenseStatus.LEDGER_READY)
        elif decision == 'not_business':
            current = repo.transition(expense_id, ExpenseStatus.NOT_BUSINESS)
        else:
            current = repo.transition(expense_id, ExpenseStatus.DUPLICATE)
        return {'expense': _serialise(current), 'events': [dict(event) for event in repo.events(expense_id)]}
    finally:
        repo.close()


def post_ready_expense(*, expense_id: str, transaction: Mapping[str, Any],
                       database: str | Path = DEFAULT_DATABASE) -> FinancePostResult:
    """Offer one reviewed expense to the sole strict SQLite finance writer."""
    repo = ExpenseRepository(database)
    try:
        return ExpenseFinanceBridge(repo, SqliteFinanceWriter(database)).post(expense_id, transaction)
    finally:
        repo.close()


def _serialise(expense: Any) -> dict[str, Any]:
    result = dict(expense.__dict__)
    result['status'] = expense.status.value
    return result


def _json_object(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('JSON input must be an object')
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Controlled SEER SQLite expense review/posting operations.')
    parser.add_argument('--database', default=str(DEFAULT_DATABASE))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    review = sub.add_parser('review')
    review.add_argument('--expense-id', required=True)
    review.add_argument('--decision', required=True, choices=('confirm', 'not_business', 'duplicate'))
    review.add_argument('--facts-json', default='{}')
    post = sub.add_parser('post')
    post.add_argument('--expense-id', required=True)
    post.add_argument('--transaction-json', required=True)
    args = parser.parse_args(argv)
    if args.command == 'list':
        output: Any = list_holding_tray(args.database)
    elif args.command == 'review':
        output = review_expense(expense_id=args.expense_id, decision=args.decision,
                                facts=_json_object(args.facts_json), database=args.database)
    else:
        outcome = post_ready_expense(expense_id=args.expense_id,
                                    transaction=_json_object(args.transaction_json), database=args.database)
        output = outcome.log_fields()
        output['status'] = outcome.status.value
        output['outcome'] = outcome.outcome.value
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

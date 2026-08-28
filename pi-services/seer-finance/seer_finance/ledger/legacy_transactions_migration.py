"""Idempotently ingest validated legacy accounting rows into canonical SQLite."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from .expense_repository import ExpenseRepository, ExpenseStatus
from .loader import parse_transaction
from .sqlite_finance_writer import SqliteFinanceWriter

def migrate(*, transactions_path: str | Path, database: str | Path) -> dict[str, int]:
    rows=json.loads(Path(transactions_path).read_text(encoding='utf-8'))
    if not isinstance(rows,list): raise ValueError('legacy transactions must be an array')
    refs=Counter(row.get('source_ref') for row in rows if isinstance(row,dict) and row.get('source_ref'))
    repo=ExpenseRepository(database); writer=SqliteFinanceWriter(database)
    result={'ledger_written':0,'exact_replay':0,'preserved_for_review':0}
    try:
      for index,row in enumerate(rows):
        if not isinstance(row,dict) or not row.get('source_ref'):
          ref=f'legacy-transactions-json:{index}'
          repo.capture(source_surface='transactions_json',source_ref=ref,evidence_ref=f'transactions.json:$[{index}]',evidence_state='retained')
          result['preserved_for_review']+=1; continue
        txn=parse_transaction(row,index)
        # Accounting income never enters the expense repository. A duplicate
        # legacy income reference remains preserved in the accounting source
        # for Tide-led reconciliation; it is not converted into an expense row.
        if txn.direction.value != 'expense':
          if refs[txn.source_ref] > 1:
            result['accounting_only_preserved'] = result.get('accounting_only_preserved', 0) + 1
            continue
          ref=writer.validate_and_write(txn)
          if ref == f'sqlite:{txn.txn_id}':
            result['accounting_ledger_written'] = result.get('accounting_ledger_written', 0) + 1
          else:
            result['accounting_exact_replay'] = result.get('accounting_exact_replay', 0) + 1
          continue
        if refs[txn.source_ref] > 1:
          ref=f'legacy-transactions-json:{index}'
          repo.capture(source_surface='transactions_json',source_ref=ref,evidence_ref=f'transactions.json:$[{index}]',evidence_state='retained')
          result['preserved_for_review']+=1; continue
        expense=repo.capture(source_surface='transactions_json',source_ref=txn.source_ref,
          supplier=txn.counterparty,amount_pence=txn.amount_pence,currency='GBP',expense_date=txn.date,
          category=txn.category.value,evidence_ref=f'transactions.json:$[{index}]',evidence_state='retained',settlement_state='confirmed')
        if expense.status is ExpenseStatus.NEEDS_REVIEW:
          expense=repo.transition(expense.expense_id,ExpenseStatus.CONFIRMED)
          expense=repo.transition(expense.expense_id,ExpenseStatus.LEDGER_READY)
        if expense.status is ExpenseStatus.LEDGER_WRITTEN:
          result['exact_replay']+=1; continue
        ref=writer.validate_and_write(txn)
        repo.finalize_ledger_write(expense.expense_id,ref)
        result['ledger_written']+=1
    finally: repo.close()
    return result

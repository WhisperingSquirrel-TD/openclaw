"""Resolve fully enriched expense candidates through the canonical SQLite writer.

This worker never derives accounting facts.  It preserves unresolved candidates
in the queue and blocks every failed hand-off with the exact reason.
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FINANCE_ROOT=Path('/home/tomdean88/pi-services/seer-finance')
if str(FINANCE_ROOT) not in sys.path: sys.path.insert(0,str(FINANCE_ROOT))
from seer_finance.ledger.expense_finance_bridge import ExpenseFinanceBridge, FinancePostOutcome
from seer_finance.ledger.expense_repository import ExpenseRepository, ExpenseStatus
from seer_finance.ledger.sqlite_finance_writer import SqliteFinanceWriter


def _write_atomic(path: Path, value: Any) -> None:
    fd,tmp=tempfile.mkstemp(prefix=f'.{path.name}.',dir=path.parent,text=True)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as h:
            json.dump(value,h,indent=2); h.write('\n'); h.flush(); os.fsync(h.fileno())
        os.replace(tmp,path)
    except Exception:
        Path(tmp).unlink(missing_ok=True); raise


def _prepare(repository: ExpenseRepository, item: dict[str, Any], transaction: dict[str, Any]):
    expense=repository.capture(source_surface=str(item.get('source_surface') or 'expense_enrichment_queue'), source_ref=item['source_id'],
        supplier=transaction['counterparty'], amount_pence=transaction['amount_pence'], currency='GBP', expense_date=transaction['date'],
        category=transaction['category'], evidence_ref=item.get('canonical_ref'), evidence_state='retained', settlement_state='confirmed')
    if expense.status is ExpenseStatus.NEEDS_REVIEW:
        expense=repository.transition(expense.expense_id,ExpenseStatus.CONFIRMED)
        expense=repository.transition(expense.expense_id,ExpenseStatus.LEDGER_READY)
    return expense


def resolve_ready_items(queue_path: Path, database_path: Path) -> dict[str,int]:
    raw=json.loads(queue_path.read_text(encoding='utf-8'))
    if not isinstance(raw,dict) or not isinstance(raw.get('items'),list): raise ValueError('enrichment queue is malformed')
    result={'written':0,'duplicates':0,'waiting':0,'blocked':0}
    repository=None; bridge=None
    try:
      for item in raw['items']:
        if not isinstance(item,dict) or item.get('state')!='needs_enrichment': continue
        enrichment=item.get('enrichment')
        if not isinstance(enrichment,dict) or enrichment.get('payment_settlement')!='confirmed' or enrichment.get('evidence_state')!='retained': result['waiting']+=1; continue
        transaction=enrichment.get('transaction')
        if not isinstance(transaction,dict) or transaction.get('source_ref')!=item.get('source_id'):
          item['state']='blocked'; item['blocker']='transaction must be complete and source_ref must exactly match queued source_id'; result['blocked']+=1; continue
        try:
          if repository is None:
            repository=ExpenseRepository(database_path)
            bridge=ExpenseFinanceBridge(repository,SqliteFinanceWriter(database_path))
          expense=_prepare(repository,item,transaction)
          post=bridge.post(expense.expense_id,transaction)
        except Exception as exc:
          item['state']='blocked'; item['blocker']=f'sqlite finance handoff failed: {type(exc).__name__}: {exc}'; result['blocked']+=1; continue
        if post.outcome is FinancePostOutcome.POSTED:
          item.update({'state':'ledger_written','ledger_state':'written','evidence_state':'retained','resolved_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'sqlite_finance_ref':post.finance_ledger_ref}); result['written']+=1
        elif post.outcome is FinancePostOutcome.ALREADY_POSTED:
          item.update({'state':'ledger_written','ledger_state':'written','evidence_state':'retained','sqlite_finance_ref':post.finance_ledger_ref}); result['duplicates']+=1
        else:
          item['state']='blocked'; item['blocker']=f'sqlite finance bridge {post.outcome.value}: {post.error_code}'; result['blocked']+=1
    finally:
      if repository is not None: repository.close()
    raw['updated_at']=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'); _write_atomic(queue_path,raw); return result


def main() -> None:
    root=Path('/home/tomdean88')
    queue=root/'.openclaw/runtime/inbound-watch-router/expense-enrichment-queue.json'
    database=root/'pi-services/seer-finance/data/expense-ledger.sqlite3'
    if not queue.exists(): print(json.dumps({'written':0,'duplicates':0,'waiting':0,'blocked':0,'queue':'absent'})); return
    print(json.dumps(resolve_ready_items(queue,database),sort_keys=True))
if __name__=='__main__': main()

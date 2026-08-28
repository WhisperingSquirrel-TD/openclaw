from __future__ import annotations
import json,tempfile,unittest
from pathlib import Path
from seer_finance.ledger.legacy_transactions_migration import migrate
from seer_finance.ledger.expense_repository import ExpenseRepository
class LegacyMigrationTests(unittest.TestCase):
 def test_imports_confirmed_rows_and_preserves_duplicate_refs(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'transactions.json'; db=root/'ledger.sqlite3'
   source.write_text(json.dumps([{'txn_id':'a','date':'2026-08-01','direction':'expense','amount_pence':100,'description':'a','counterparty':'A','category':'software','source_ref':'a'}, {'txn_id':'b','date':'2026-08-02','direction':'expense','amount_pence':200,'description':'b','counterparty':'B','category':'software','source_ref':'dup'}, {'txn_id':'c','date':'2026-08-03','direction':'expense','amount_pence':300,'description':'c','counterparty':'C','category':'software','source_ref':'dup'}]))
   self.assertEqual({'ledger_written':1,'exact_replay':0,'preserved_for_review':2},migrate(transactions_path=source,database=db))
   self.assertEqual({'ledger_written':0,'exact_replay':1,'preserved_for_review':2},migrate(transactions_path=source,database=db))
   repo=ExpenseRepository(db)
   try: self.assertEqual(3,repo.connection.execute('select count(*) from expenses').fetchone()[0])
   finally: repo.close()
 def test_income_never_creates_expense_review_record(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'transactions.json'; db=root/'ledger.sqlite3'
   source.write_text(json.dumps([
    {'txn_id':'income-a','date':'2026-08-01','direction':'income','amount_pence':4000,'description':'PT income','counterparty':'Client A','category':'sales','source_ref':'Tide:2026-08-01:PT-A'},
    {'txn_id':'income-b','date':'2026-08-02','direction':'income','amount_pence':4000,'description':'PT income','counterparty':'Client B','category':'sales','source_ref':'Tide:2026-08-02:PT-duplicate'},
    {'txn_id':'income-c','date':'2026-08-02','direction':'income','amount_pence':4000,'description':'PT income','counterparty':'Client C','category':'sales','source_ref':'Tide:2026-08-02:PT-duplicate'},
    {'txn_id':'expense-a','date':'2026-08-03','direction':'expense','amount_pence':100,'description':'software','counterparty':'Supplier','category':'software','source_ref':'Tide:2026-08-03:software'}
   ]))
   result=migrate(transactions_path=source,database=db)
   self.assertEqual(1,result['accounting_ledger_written'])
   self.assertEqual(2,result['accounting_only_preserved'])
   repo=ExpenseRepository(db)
   try:
    self.assertEqual(1,repo.connection.execute('select count(*) from expenses').fetchone()[0])
    self.assertEqual(1,repo.connection.execute('select count(*) from finance_transactions where txn_id=?',('income-a',)).fetchone()[0])
    self.assertEqual(0,repo.connection.execute("select count(*) from expenses where source_ref like 'Tide:%PT%'").fetchone()[0])
   finally: repo.close()
if __name__=='__main__':unittest.main()

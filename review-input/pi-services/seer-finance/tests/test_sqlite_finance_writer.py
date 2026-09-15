from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from seer_finance.ledger.expense_finance_bridge import FinanceReferenceConflict
from seer_finance.ledger.schema import Category, Direction, Transaction
from seer_finance.ledger.sqlite_finance_writer import SqliteFinanceWriter

class SqliteFinanceWriterTests(unittest.TestCase):
 def setUp(self): self.temp=tempfile.TemporaryDirectory(); self.db=Path(self.temp.name)/'ledger.sqlite3'; self.writer=SqliteFinanceWriter(self.db)
 def tearDown(self): self.temp.cleanup()
 def txn(self, amount=1200): return Transaction('expense-1','2026-08-10',Direction.EXPENSE,amount,'Test expense','Acme',Category.SOFTWARE,source_ref='email:1')
 def test_writes_once_and_exact_replay_returns_original_reference(self):
  self.assertEqual('sqlite:expense-1', self.writer.validate_and_write(self.txn()))
  self.assertEqual('sqlite:expense-1', self.writer.validate_and_write(self.txn()))
 def test_conflicting_source_reference_is_refused(self):
  self.writer.validate_and_write(self.txn())
  with self.assertRaises(FinanceReferenceConflict): self.writer.validate_and_write(self.txn(1300))

if __name__ == '__main__': unittest.main()

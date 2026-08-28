from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from seer_finance.ledger.expense_repository import ExpenseRepository
from seer_finance.ledger.database_review_snapshot import build_snapshot
class TestSnapshot(unittest.TestCase):
 def test_only_unresolved_records_are_visible(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'x.sqlite3'; r=ExpenseRepository(db)
   try:
    a=r.capture(source_surface='x',source_ref='a'); b=r.capture(source_surface='x',source_ref='b'); r.transition(b.expense_id,'not_business')
   finally:r.close()
   s=build_snapshot(db); self.assertEqual(1,s['summary']['needs_review']); self.assertEqual(['a'],[x['source_ref'] for x in s['items']])
if __name__=='__main__':unittest.main()

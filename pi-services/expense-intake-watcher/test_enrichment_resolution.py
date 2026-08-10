from __future__ import annotations
import json,tempfile,unittest
from pathlib import Path
from enrichment_resolution import resolve_ready_items
class Tests(unittest.TestCase):
 def tx(self): return {'txn_id':'expense-obcn-42','date':'2026-08-10','direction':'expense','amount_pence':4200,'description':'OBCN breakfast','counterparty':'OBCN','category':'marketing','source_ref':'obcn-42'}
 def queue(self,path,enrichment): path.write_text(json.dumps({'schema_version':1,'items':[{'source_id':'obcn-42','source_surface':'test','canonical_ref':'test:1','state':'needs_enrichment','enrichment':enrichment}]}))
 def test_confirmed_enrichment_writes_sqlite_once(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); q=root/'queue.json'; db=root/'ledger.sqlite3'; e={'payment_settlement':'confirmed','evidence_state':'retained','transaction':self.tx()}; self.queue(q,e)
   self.assertEqual({'written':1,'duplicates':0,'waiting':0,'blocked':0},resolve_ready_items(q,db)); self.assertEqual('ledger_written',json.loads(q.read_text())['items'][0]['state'])
   self.queue(q,e); self.assertEqual({'written':0,'duplicates':1,'waiting':0,'blocked':0},resolve_ready_items(q,db))
 def test_missing_enrichment_cannot_write(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); q=root/'queue.json'; db=root/'ledger.sqlite3'; self.queue(q,None)
   self.assertEqual(1,resolve_ready_items(q,db)['waiting']); self.assertFalse(db.exists())
if __name__=='__main__': unittest.main()

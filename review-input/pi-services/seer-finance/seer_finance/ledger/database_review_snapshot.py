"""Read-only operational review snapshot from the canonical SQLite ledger."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path

def build_snapshot(database: str|Path) -> dict:
 con=sqlite3.connect(str(database)); con.row_factory=sqlite3.Row
 try:
  rows=[dict(r) for r in con.execute("select expense_id,source_surface,source_ref,status,source_timestamp,observed_timestamp,supplier,amount_pence,currency,expense_date,category,evidence_ref,evidence_state,settlement_state,validation_result,created_at,updated_at from expenses where status in ('needs_review','blocked') order by observed_timestamp,expense_id")]
  return {'generated_at':datetime.now(timezone.utc).isoformat(),'database':str(database),'read_only':True,'summary':{'needs_review':sum(r['status']=='needs_review' for r in rows),'blocked':sum(r['status']=='blocked' for r in rows)},'items':rows}
 finally: con.close()
def write_snapshot(database: str|Path, output: str|Path) -> dict:
 value=build_snapshot(database); p=Path(output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); return value

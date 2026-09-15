"""Read-only review snapshot from SharePoint authority or explicit SQLite recovery input.

With no database argument this reads the SharePoint cache. SQLite is supported
only when a caller explicitly supplies a migration/recovery database.
"""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sharepoint_contract import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_QUEUE_PATH,
    DEFAULT_RESULTS_PATH,
    SharePointDocumentStore,
)
from .sharepoint_repository import SharePointExpenseRepository

def build_snapshot(database: str|Path|None = None, *,
                   sharepoint_store: SharePointDocumentStore | None = None,
                   sharepoint_queue: str|Path = DEFAULT_QUEUE_PATH,
                   sharepoint_results: str|Path = DEFAULT_RESULTS_PATH,
                   sharepoint_cache: str|Path = DEFAULT_CACHE_ROOT) -> dict[str, Any]:
 if database is None:
  repo = SharePointExpenseRepository(
   store=sharepoint_store or SharePointDocumentStore(
    queue_path=sharepoint_queue, results_path=sharepoint_results, cache_root=sharepoint_cache
   )
  )
  rows = repo.holding_tray()
  rows.sort(key=lambda row: (row['observed_timestamp'], row['expense_id']))
  return {
   'generated_at': datetime.now(timezone.utc).isoformat(),
   'authority': 'sharepoint',
   'read_only': True,
   'summary': {'needs_review': sum(r['status']=='needs_review' for r in rows), 'blocked': sum(r['status']=='blocked' for r in rows)},
   'items': rows,
  }
 con=sqlite3.connect(str(database)); con.row_factory=sqlite3.Row
 try:
  rows=[dict(r) for r in con.execute("select expense_id,source_surface,source_ref,status,source_timestamp,observed_timestamp,supplier,amount_pence,currency,expense_date,category,evidence_ref,evidence_state,settlement_state,validation_result,created_at,updated_at from expenses where status in ('needs_review','blocked') order by observed_timestamp,expense_id")]
  return {'generated_at':datetime.now(timezone.utc).isoformat(),'authority':'sqlite_recovery_input','database':str(database),'read_only':True,'summary':{'needs_review':sum(r['status']=='needs_review' for r in rows),'blocked':sum(r['status']=='blocked' for r in rows)},'items':rows}
 finally: con.close()

def write_snapshot(database: str|Path|None, output: str|Path, **kwargs: Any) -> dict:
 value=build_snapshot(database, **kwargs); p=Path(output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); return value

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path('/home/tomdean88')
WATCHER_DIR = ROOT / 'openclaw/pi-services/expense-intake-watcher'
FINANCE_DIR = ROOT / 'pi-services/seer-finance'
sys.path[:0] = [str(WATCHER_DIR), str(FINANCE_DIR)]
_spec = importlib.util.spec_from_file_location('receipt_chain_watcher', WATCHER_DIR / 'watcher.py')
assert _spec and _spec.loader
watcher = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = watcher
_spec.loader.exec_module(watcher)

from seer_finance.ledger.expense_repository import ExpenseRepository


def test_replay_receipt_is_idempotently_captured_queued_and_proved(tmp_path, monkeypatch):
    receipt = tmp_path / 'telegram-receipt.jpg'
    receipt.write_bytes(b'original-receipt-binary')
    digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
    replay = tmp_path / 'expense-sqlite-replay.json'
    database = tmp_path / 'expenses.sqlite3'
    queue = tmp_path / 'sharepoint-queue.json'
    results = tmp_path / 'sharepoint-queue-results.json'
    replay.write_text(json.dumps({'schema_version': 1, 'items': [{
        'source_surface': 'telegram_inbound', 'source_ref': 'telegram:chat:42:99',
        'facts': {'supplier': 'Example Ltd', 'source_timestamp': '2026-08-14T19:00:00Z',
                  'receipt_path': str(receipt), 'receipt_mime_type': 'image/jpeg'},
        'blocker': 'sqlite_capture_failed:OperationalError:test',
    }]}))
    monkeypatch.setattr(watcher, 'SHAREPOINT_QUEUE_FILE', queue)
    monkeypatch.setattr(watcher, 'SHAREPOINT_RESULTS_FILE', results)

    first = watcher.process_expense_sqlite_replay({}, replay_path=replay, database=database)
    assert first[0]['state'] == 'blocked'
    assert first[0]['blocker'] == 'sharepoint_upload_pending'
    queued = json.loads(queue.read_text())
    assert queued[0]['operation'] == 'upload_binary'
    assert queued[0]['mime_type'] == 'image/jpeg'
    assert queued[0]['source_path'] == str(receipt)

    upload_id = queued[0]['id']
    results.write_text(json.dumps([{
        'id': upload_id, 'success': True,
        'output': json.dumps({'status': 'uploaded', 'url': 'https://sharepoint/receipt', 'etag': '"etag-1"'}),
    }]))
    second = watcher.process_expense_sqlite_replay({}, replay_path=replay, database=database)
    assert second[0]['state'] == 'success'
    assert second[0]['source_ref'] == 'telegram:chat:42:99'
    assert second[0]['expense_id']
    assert second[0]['sharepoint_url'] == 'https://sharepoint/receipt'
    assert second[0]['sharepoint_etag'] == '"etag-1"'
    assert json.loads(replay.read_text())['items'] == []

    repository = ExpenseRepository(database)
    try:
        evidence = repository.receipt_evidence('telegram:chat:42:99')
        assert [(item.evidence_kind, item.sha256) for item in evidence] == [
            ('local_receipt_binary', digest), ('sharepoint_receipt_binary', digest),
        ]
        # A repeat cannot duplicate immutable evidence after replay has closed.
        assert watcher.process_expense_sqlite_replay({}, replay_path=replay, database=database) == []
        assert len(repository.receipt_evidence('telegram:chat:42:99')) == 2
    finally:
        repository.close()


def test_replay_without_original_binary_stays_blocked(tmp_path, monkeypatch):
    replay = tmp_path / 'expense-sqlite-replay.json'
    database = tmp_path / 'expenses.sqlite3'
    replay.write_text(json.dumps({'items': [{
        'source_surface': 'telegram_inbound', 'source_ref': 'telegram:chat:missing',
        'facts': {'receipt_path': str(tmp_path / 'missing.jpg')},
    }]}))
    monkeypatch.setattr(watcher, 'SHAREPOINT_QUEUE_FILE', tmp_path / 'queue.json')
    monkeypatch.setattr(watcher, 'SHAREPOINT_RESULTS_FILE', tmp_path / 'results.json')

    states = watcher.process_expense_sqlite_replay({}, replay_path=replay, database=database)
    assert states[0]['state'] == 'blocked'
    assert states[0]['blocker'] == 'original_receipt_binary_unavailable'
    assert len(json.loads(replay.read_text())['items']) == 1

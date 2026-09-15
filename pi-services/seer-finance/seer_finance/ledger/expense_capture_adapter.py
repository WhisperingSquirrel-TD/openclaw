"""Single-writer capture boundary for live expense candidates.

The adapter accepts only source-linked facts, captures them in SQLite without
inventing financial values, and preserves a durable replay record when the
ledger cannot be safely written.  It performs no finance posting.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .expense_repository import ExpenseRepository
from .sharepoint_contract import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_QUEUE_PATH,
    DEFAULT_RESULTS_PATH,
    SharePointDocumentStore,
)
from .sharepoint_repository import SharePointExpenseRepository

# SQLite is intentionally opt-in for migration/recovery compatibility.  Live
# capture defaults to the authoritative SharePoint queue/cache boundary.
DEFAULT_DATABASE: Path | None = None
DEFAULT_REPLAY = Path(os.environ.get('SEER_FINANCE_REPLAY', '/var/lib/seer-finance/expense-replay.json'))


@dataclass(frozen=True)
class CaptureResult:
    outcome: str  # captured | replayed | accounting_only
    expense_id: str | None
    source_ref: str
    blocker: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def _append_replay(path: Path, *, source_surface: str, source_ref: str,
                   facts: Mapping[str, Any], blocker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + '.writer.lock')
    with lock_path.open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            try:
                current = json.loads(path.read_text(encoding='utf-8'))
            except FileNotFoundError:
                current = {'schema_version': 1, 'items': []}
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RuntimeError('replay manifest malformed') from exc
            if not isinstance(current, dict) or not isinstance(current.get('items'), list):
                raise RuntimeError('replay manifest malformed')
            existing = next(
                (
                    item for item in current['items']
                    if isinstance(item, dict) and item.get('source_ref') == source_ref
                ),
                None,
            )
            if existing is None:
                current['items'].append({
                    'source_surface': source_surface,
                    'source_ref': source_ref,
                    'facts': dict(facts),
                    'blocker': blocker,
                    'observed_at': _now(),
                })
            else:
                # A retry for the same source is idempotent, but a later
                # attempt may have transport metadata that was unavailable on
                # the first failure.  Retain existing facts and only enrich
                # fields that were previously absent.
                existing_facts = existing.get('facts')
                if isinstance(existing_facts, dict):
                    for key, value in facts.items():
                        if value is not None and existing_facts.get(key) is None:
                            existing_facts[key] = value
            current['updated_at'] = _now()
            _atomic_json(path, current)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def capture_candidate(*, source_surface: str, source_ref: str,
                      facts: Mapping[str, Any] | None = None,
                      database: str | Path | None = DEFAULT_DATABASE,
                      replay_path: str | Path = DEFAULT_REPLAY,
                      sharepoint_store: SharePointDocumentStore | None = None,
                      sharepoint_queue: str | Path = DEFAULT_QUEUE_PATH,
                      sharepoint_results: str | Path = DEFAULT_RESULTS_PATH,
                      sharepoint_cache: str | Path = DEFAULT_CACHE_ROOT) -> CaptureResult:
    """Capture once, or retain a source-linked replay item on any safe failure."""
    if not isinstance(source_surface, str) or not source_surface.strip():
        raise ValueError('source_surface is required')
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError('source_ref is required')
    replay_facts = dict(facts or {})
    safe_facts = dict(replay_facts)
    # Receipt transport metadata is deliberately not an expense fact.  It is
    # consumed by the replay worker after capture to create immutable evidence.
    for transport_key in ("receipt_path", "receipt_local_path", "receipt_mime_type", "receipt_filename"):
        safe_facts.pop(transport_key, None)
    # This boundary owns expenses, not revenue. Callers retaining an explicit
    # income/non-expense source must route it to finance reconciliation while
    # preserving its upstream evidence; it must never become an expense row.
    direction = safe_facts.pop('direction', None)
    replay_facts.pop('direction', None)
    if direction is not None and direction != 'expense':
        return CaptureResult('accounting_only', None, source_ref,
                             f'explicit_non_expense_direction:{direction}')
    # Let the repository stamp first capture.  Supplying a fresh observed time
    # on every retry would turn an otherwise idempotent replay into a collision.
    database_path = Path(database) if database is not None else None
    replay = Path(replay_path)
    lock_path = (
        database_path.with_suffix(database_path.suffix + '.writer.lock')
        if database_path is not None
        else replay.with_suffix(replay.suffix + '.sharepoint.writer.lock')
    )
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open('a+') as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('expense ledger writer busy')
            try:
                repository = (
                    ExpenseRepository(database_path)
                    if database_path is not None
                    else SharePointExpenseRepository(
                        store=sharepoint_store or SharePointDocumentStore(
                            queue_path=sharepoint_queue,
                            results_path=sharepoint_results,
                            cache_root=sharepoint_cache,
                        )
                    )
                )
                try:
                    expense = repository.capture(source_surface=source_surface, source_ref=source_ref, **safe_facts)
                finally:
                    repository.close()
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        return CaptureResult('captured', expense.expense_id, source_ref)
    except Exception as exc:
        authority = 'sqlite' if database_path is not None else 'sharepoint'
        blocker = f'{authority}_capture_failed:{type(exc).__name__}:{exc}'
        _append_replay(replay, source_surface=source_surface, source_ref=source_ref,
                       facts=replay_facts, blocker=blocker)
        return CaptureResult('replayed', None, source_ref, blocker)

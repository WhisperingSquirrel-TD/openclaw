#!/usr/bin/env python3
"""Durable, fail-closed primitives for first-class inbound intake.

The ledger separates canonical source events, route receipts, and surface health.
It deliberately records only internal operational state; route workers remain
responsible for their existing approval gates and destination writes.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_ROOT = Path("/home/tomdean88/.openclaw/workspace/memory")
EVENTS_FILE = "intake-events.jsonl"
RECEIPTS_FILE = "intake-route-receipts.jsonl"
HEALTH_FILE = "intake-surface-health.json"

RECEIPT_STATES = {"pending", "queued", "verified", "blocked", "coverage_incomplete", "not_needed"}
TERMINAL_RECEIPT_STATES = {"verified", "blocked", "coverage_incomplete", "not_needed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_event_id(*, surface: str, provider_event_id: str | None, provider_conversation_id: str | None) -> str:
    """Return a deterministic ID only when the provider gave a receipt-safe identity."""
    item = str(provider_event_id or "").strip()
    conversation = str(provider_conversation_id or "").strip()
    if not item and not conversation:
        raise ValueError("canonical event requires provider_event_id or provider_conversation_id")
    material = "\x1f".join((surface.strip(), item, conversation)).encode("utf-8")
    return "evt-" + hashlib.sha256(material).hexdigest()[:24]


@contextmanager
def _locked(root: Path, name: str) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    with (root / f".{name}.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"invalid ledger row in {path.name}")
        rows.append(row)
    return rows


def _atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def record_event(event: dict[str, Any], *, root: Path = DEFAULT_ROOT) -> tuple[dict[str, Any], bool]:
    """Persist one logical event exactly once; later aliases enrich, never duplicate it."""
    required = {"surface", "provider_event_id", "provider_conversation_id", "source_timestamp", "observed_at", "evidence_refs", "identity_state", "classification", "confidence", "entity_state", "entity_refs", "route_set"}
    missing = sorted(key for key in required if key not in event)
    if missing:
        raise ValueError("event missing required fields: " + ", ".join(missing))
    event_id = canonical_event_id(surface=str(event["surface"]), provider_event_id=event.get("provider_event_id"), provider_conversation_id=event.get("provider_conversation_id"))
    candidate = {**event, "event_id": event_id}
    candidate["evidence_refs"] = sorted(set(str(v) for v in event.get("evidence_refs") or []))
    candidate["entity_refs"] = sorted(set(str(v) for v in event.get("entity_refs") or []))
    candidate["route_set"] = sorted(set(str(v) for v in event.get("route_set") or []))
    path = root / EVENTS_FILE
    with _locked(root, EVENTS_FILE):
        rows = _read_jsonl(path)
        for index, row in enumerate(rows):
            if row.get("event_id") != event_id:
                continue
            merged = {**row, **candidate}
            merged["evidence_refs"] = sorted(set(row.get("evidence_refs") or []) | set(candidate["evidence_refs"]))
            merged["entity_refs"] = sorted(set(row.get("entity_refs") or []) | set(candidate["entity_refs"]))
            merged["route_set"] = sorted(set(row.get("route_set") or []) | set(candidate["route_set"]))
            rows[index] = merged
            _atomic_jsonl(path, rows)
            return merged, False
        rows.append(candidate)
        _atomic_jsonl(path, rows)
    return candidate, True


def record_receipt(receipt: dict[str, Any], *, root: Path = DEFAULT_ROOT) -> tuple[dict[str, Any], bool]:
    """Upsert a worker receipt keyed by (event_id, route), preserving attempt history."""
    required = {"event_id", "route", "state", "owner", "evidence_ref", "destination_ref", "error_code", "next_review_at"}
    missing = sorted(key for key in required if key not in receipt)
    if missing:
        raise ValueError("receipt missing required fields: " + ", ".join(missing))
    if receipt["state"] not in RECEIPT_STATES:
        raise ValueError(f"invalid receipt state: {receipt['state']}")
    path = root / RECEIPTS_FILE
    with _locked(root, RECEIPTS_FILE):
        rows = _read_jsonl(path)
        prior = next((row for row in rows if row.get("event_id") == receipt["event_id"] and row.get("route") == receipt["route"]), None)
        timestamp = now_iso()
        attempt = int(prior.get("attempt") or 0) + 1 if prior else 1
        current = {**(prior or {}), **receipt, "attempt": attempt, "created_at": (prior or {}).get("created_at", timestamp), "updated_at": timestamp}
        if prior:
            rows[rows.index(prior)] = current
        else:
            rows.append(current)
        _atomic_jsonl(path, rows)
    return current, prior is None


def update_surface_health(surface: str, update: dict[str, Any], *, root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    """Atomically upsert one first-class surface health row without claiming clean coverage."""
    required = {"cadence", "last_successful_visible_update", "watermark", "last_attempt", "captured_count", "routed_count", "verified_count", "blocked_count", "duplicate_count", "oldest_blocker", "last_error", "runtime_duration_ms", "coverage_state"}
    missing = sorted(key for key in required if key not in update)
    if missing:
        raise ValueError("surface health missing required fields: " + ", ".join(missing))
    if update["coverage_state"] not in {"clean", "blocked", "coverage_incomplete"}:
        raise ValueError("invalid coverage_state")
    path = root / HEALTH_FILE
    with _locked(root, HEALTH_FILE):
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "surfaces": {}}
        payload.setdefault("surfaces", {})[surface] = {**update, "surface": surface, "updated_at": now_iso()}
        fd, temporary = tempfile.mkstemp(prefix=f".{HEALTH_FILE}.", suffix=".tmp", dir=root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise
    return payload["surfaces"][surface]

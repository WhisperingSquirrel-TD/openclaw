"""Bounded, source-linked enrichment queue for expense candidates.

The queue holds only unresolved financial facts. It is not a second expense
ledger: canonical outcome remains seer-expenses.md and accounting truth remains
the finance ledger.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_FACTS = ("amount_pence", "category", "payment_settlement", "evidence_state")


def _write_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def enqueue(queue_path: Path, *, source_id: str, source_surface: str,
            canonical_ref: str, blocker: str, observed_at: str | None = None,
            raw_source_timestamp: str | None = None,
            source_timestamp_status: str = "valid") -> bool:
    """Add one unresolved candidate once; return False for a replay."""
    if not all((source_id, source_surface, canonical_ref, blocker)):
        raise ValueError("source_id, source_surface, canonical_ref and blocker are required")
    try:
        raw = json.loads(queue_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {"schema_version": 1, "items": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("items", []), list):
        raise ValueError("enrichment queue is malformed")
    items = raw["items"]
    if any(isinstance(item, dict) and item.get("source_id") == source_id for item in items):
        return False
    items.append({
        "source_id": source_id,
        "source_surface": source_surface,
        "canonical_ref": canonical_ref,
        "state": "needs_enrichment",
        "required_facts": list(REQUIRED_FACTS),
        "blocker": blocker,
        "observed_at": observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw_source_timestamp": raw_source_timestamp,
        "source_timestamp_status": source_timestamp_status,
    })
    raw["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_atomic(queue_path, raw)
    return True

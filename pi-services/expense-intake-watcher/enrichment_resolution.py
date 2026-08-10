"""Resolve enriched expense candidates into the validated finance ledger.

Resolution is intentionally opt-in: a queue item stays `needs_enrichment` until
an authorised enrichment process supplies exact financial facts and retained
evidence. This worker never guesses or derives those facts from mirror text.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finance_handoff import TransactionValidationError, append_validated_expense


def _write_atomic(path: Path, value: Any) -> None:
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


def resolve_ready_items(queue_path: Path, ledger_path: Path) -> dict[str, int]:
    raw = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise ValueError("enrichment queue is malformed")
    result = {"written": 0, "duplicates": 0, "waiting": 0, "blocked": 0}
    for item in raw["items"]:
        if not isinstance(item, dict) or item.get("state") != "needs_enrichment":
            continue
        enrichment = item.get("enrichment")
        if not isinstance(enrichment, dict):
            result["waiting"] += 1
            continue
        if enrichment.get("payment_settlement") != "confirmed" or enrichment.get("evidence_state") != "retained":
            result["waiting"] += 1
            continue
        transaction = enrichment.get("transaction")
        if not isinstance(transaction, dict):
            item["state"] = "blocked"
            item["blocker"] = "enrichment lacks complete transaction object"
            result["blocked"] += 1
            continue
        if transaction.get("source_ref") != item.get("source_id"):
            item["state"] = "blocked"
            item["blocker"] = "transaction source_ref must exactly match queued source_id"
            result["blocked"] += 1
            continue
        try:
            created = append_validated_expense(ledger_path, transaction)
        except (TransactionValidationError, ValueError) as exc:
            item["state"] = "blocked"
            item["blocker"] = f"finance validation failed: {exc}"
            result["blocked"] += 1
            continue
        item["state"] = "ledger_written"
        item["ledger_state"] = "written"
        item["evidence_state"] = "retained"
        item["resolved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result["written" if created else "duplicates"] += 1
    raw["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_atomic(queue_path, raw)
    return result


def main() -> None:
    root = Path('/home/tomdean88')
    queue_path = root / '.openclaw' / 'runtime' / 'inbound-watch-router' / 'expense-enrichment-queue.json'
    ledger_path = root / 'pi-services' / 'seer-finance' / 'transactions.json'
    if not queue_path.exists():
        print(json.dumps({"written": 0, "duplicates": 0, "waiting": 0, "blocked": 0, "queue": "absent"}))
        return
    print(json.dumps(resolve_ready_items(queue_path, ledger_path), sort_keys=True))


if __name__ == '__main__':
    main()

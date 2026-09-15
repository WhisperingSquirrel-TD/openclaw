"""Resolve enriched candidates through the SharePoint finance authority.

The JSON file is a retry queue only.  It is never a ledger and it cannot
complete a candidate without a verified write/readback from seer-finance.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finance_handoff import update_validated_expense
from sharepoint_boundary import SharePointBoundary, resolve_boundary


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


def resolve_ready_items(
    queue_path: Path,
    boundary: SharePointBoundary | None = None,
) -> dict[str, int]:
    raw = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise ValueError("enrichment queue is malformed")
    result = {"written": 0, "duplicates": 0, "waiting": 0, "blocked": 0}
    authority = boundary or resolve_boundary()
    for item in raw["items"]:
        if not isinstance(item, dict) or item.get("state") != "needs_enrichment":
            continue
        enrichment = item.get("enrichment")
        if (
            not isinstance(enrichment, dict)
            or enrichment.get("payment_settlement") != "confirmed"
            or enrichment.get("evidence_state") != "retained"
        ):
            result["waiting"] += 1
            continue
        transaction = enrichment.get("transaction")
        if not isinstance(transaction, dict) or transaction.get("source_ref") != item.get("source_id"):
            item["state"] = "blocked"
            item["blocker"] = (
                "transaction must be complete and source_ref must exactly match queued source_id"
            )
            result["blocked"] += 1
            continue
        if transaction.get("direction") != "expense":
            item.update({
                "state": "accounting_only",
                "ledger_state": "not_expense",
                "blocker": (
                    f"explicit transaction direction {transaction.get('direction')!r}; "
                    "excluded from expense workflow"
                ),
            })
            result["waiting"] += 1
            continue
        try:
            handoff = update_validated_expense(authority, transaction)
        except Exception as exc:
            item["state"] = "blocked"
            item["blocker"] = (
                f"SharePoint finance handoff failed: {type(exc).__name__}: {exc}"
            )
            result["blocked"] += 1
            continue
        if handoff.complete:
            item.update({
                "state": "ledger_written",
                "ledger_state": "written",
                "evidence_state": "retained",
                "resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "finance_ledger_ref": handoff.canonical_ref,
            })
            result["written"] += 1
        elif handoff.accepted:
            item["blocker"] = handoff.blocker or "SharePoint readback pending"
            result["waiting"] += 1
        else:
            item["state"] = "blocked"
            item["blocker"] = handoff.blocker or "SharePoint finance handoff was not accepted"
            result["blocked"] += 1
    raw["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_atomic(queue_path, raw)
    return result


def main() -> None:
    root = Path(os.environ.get("OPENCLAW_ROOT", str(Path.home())))
    queue = root / ".openclaw/runtime/inbound-watch-router/expense-enrichment-queue.json"
    if not queue.exists():
        print(json.dumps({"written": 0, "duplicates": 0, "waiting": 0, "blocked": 0, "queue": "absent"}))
        return
    print(json.dumps(resolve_ready_items(queue), sort_keys=True))


if __name__ == "__main__":
    main()
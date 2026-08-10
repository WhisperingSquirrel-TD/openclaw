"""Fail-closed bridge from an exact expense outcome to the SEER finance ledger.

No caller may infer a category, amount or payment source. This module only admits
an already-complete transaction object, validates the complete existing ledger
and candidate with the finance engine, and atomically appends it once.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

FINANCE_ROOT = Path('/home/tomdean88/pi-services/seer-finance')
if str(FINANCE_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_ROOT))

from seer_finance.ledger.loader import TransactionValidationError, load_transactions, parse_transaction


def append_validated_expense(ledger_path: Path, candidate: dict[str, Any]) -> bool:
    """Append a fully specified, source-linked transaction exactly once.

    Returns False for a stable duplicate source reference. Raises a validation
    error for incomplete/malformed records, preserving the caller's `blocked`
    outcome rather than guessing financial data.
    """
    existing = json.loads(ledger_path.read_text(encoding='utf-8'))
    if not isinstance(existing, list):
        raise TransactionValidationError('ledger top level must be a JSON array')
    parsed = parse_transaction(candidate, len(existing))
    source_ref = parsed.source_ref
    if not source_ref:
        raise TransactionValidationError('expense ledger handoff requires source_ref')
    for row in existing:
        if isinstance(row, dict) and row.get('source_ref') == source_ref:
            return False
    # Validate existing data before mutation and the complete proposed ledger.
    load_transactions(ledger_path)
    proposed = [*existing, candidate]
    fd, temp_name = tempfile.mkstemp(prefix=f'.{ledger_path.name}.', dir=ledger_path.parent, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(proposed, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        load_transactions(temp_name)
        os.replace(temp_name, ledger_path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return True

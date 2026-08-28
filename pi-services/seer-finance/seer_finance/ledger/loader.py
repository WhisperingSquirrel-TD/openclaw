"""
Validating loader for SEER transaction data.

OpenClaw produces a JSON array of transaction objects in the agreed format
(see FORMAT.md). This loader validates every field strictly and rejects
malformed input rather than coercing it, because silent coercion of financial
data hides errors that later surface as wrong tax figures.

Security / correctness posture:
  - Money must arrive as an integer number of pence. Strings, floats, and
    negative values are rejected. This prevents float rounding entering the
    ledger and prevents sign-convention confusion.
  - Every enum-valued field must match the controlled vocabulary exactly;
    unknown categories or treatments are errors, not warnings.
  - Dates must be valid ISO calendar dates.
  - Unknown top-level keys are rejected, so a typo'd field name cannot silently
    drop data.
  - The loader never executes or evals any input; it only reads JSON values.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .schema import Category, Direction, TaxTreatment, Transaction

_ALLOWED_KEYS = {
    "txn_id", "date", "direction", "amount_pence", "description",
    "counterparty", "category", "pre_trading", "tax_treatment", "source_ref",
}
_REQUIRED_KEYS = {
    "txn_id", "date", "direction", "amount_pence", "description",
    "counterparty", "category",
}


class TransactionValidationError(ValueError):
    """Raised when a transaction record fails validation."""


def _require_iso_date(value: object, ctx: str) -> str:
    if not isinstance(value, str):
        raise TransactionValidationError(f"{ctx}: date must be a string")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise TransactionValidationError(f"{ctx}: invalid date {value!r}") from exc
    return value


def _require_pence(value: object, ctx: str) -> int:
    # Reject bool explicitly: bool is a subclass of int in Python.
    if isinstance(value, bool) or not isinstance(value, int):
        raise TransactionValidationError(
            f"{ctx}: amount_pence must be an integer number of pence "
            f"(got {value!r}); do not send pounds or floats"
        )
    if value < 0:
        raise TransactionValidationError(
            f"{ctx}: amount_pence must be non-negative; use `direction` for sign"
        )
    return value


def _require_enum(value: object, enum_cls, ctx: str, field: str):
    if not isinstance(value, str):
        raise TransactionValidationError(f"{ctx}: {field} must be a string")
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = ", ".join(e.value for e in enum_cls)
        raise TransactionValidationError(
            f"{ctx}: unknown {field} {value!r}; allowed: {allowed}"
        ) from exc


def _require_str(value: object, ctx: str, field: str) -> str:
    if not isinstance(value, str):
        raise TransactionValidationError(f"{ctx}: {field} must be a string")
    return value


def parse_transaction(obj: dict, index: int) -> Transaction:
    ctx = f"transaction[{index}]"
    if not isinstance(obj, dict):
        raise TransactionValidationError(f"{ctx}: must be an object")

    keys = set(obj.keys())
    unknown = keys - _ALLOWED_KEYS
    if unknown:
        raise TransactionValidationError(
            f"{ctx}: unknown field(s) {sorted(unknown)}"
        )
    missing = _REQUIRED_KEYS - keys
    if missing:
        raise TransactionValidationError(
            f"{ctx}: missing required field(s) {sorted(missing)}"
        )

    treatment = None
    if obj.get("tax_treatment") is not None:
        treatment = _require_enum(
            obj["tax_treatment"], TaxTreatment, ctx, "tax_treatment"
        )

    pre_trading = obj.get("pre_trading", False)
    if not isinstance(pre_trading, bool):
        raise TransactionValidationError(f"{ctx}: pre_trading must be boolean")

    return Transaction(
        txn_id=_require_str(obj["txn_id"], ctx, "txn_id"),
        date=_require_iso_date(obj["date"], ctx),
        direction=_require_enum(obj["direction"], Direction, ctx, "direction"),
        amount_pence=_require_pence(obj["amount_pence"], ctx),
        description=_require_str(obj["description"], ctx, "description"),
        counterparty=_require_str(obj["counterparty"], ctx, "counterparty"),
        category=_require_enum(obj["category"], Category, ctx, "category"),
        pre_trading=pre_trading,
        tax_treatment=treatment,
        source_ref=_require_str(obj.get("source_ref", ""), ctx, "source_ref"),
    )


def load_transactions(path: str | Path) -> list[Transaction]:
    """Load and validate a JSON array of transactions from disk."""
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise TransactionValidationError("top level must be a JSON array")

    txns = [parse_transaction(obj, i) for i, obj in enumerate(data)]

    # Duplicate txn_id is almost always a double-import bug; reject it.
    seen: set[str] = set()
    for t in txns:
        if t.txn_id in seen:
            raise TransactionValidationError(f"duplicate txn_id {t.txn_id!r}")
        seen.add(t.txn_id)
    return txns

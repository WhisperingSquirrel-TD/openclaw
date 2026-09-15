#!/usr/bin/env python3
"""Pure, deterministic proposal builder for invoice-payment reconciliation.

This module does *not* read or write a ledger, tracker, database, or any remote
service.  It turns an outgoing ``INV`` message and one observed payment into a
receipt proposal which a separately-approved workflow may review.

Amounts are accepted as integer minor units (recommended) or decimal strings.
They are compared exactly with :class:`decimal.Decimal`; floats are rejected.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


RECEIPT_STATES = frozenset({"pending", "blocked", "verified"})
CLASSIFICATIONS = frozenset({"exact", "partial", "duplicate", "ambiguous"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _amount(value: Any, field: str) -> Decimal:
    """Parse an exact non-negative monetary amount without rounding."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{field} must be an integer minor-unit value or decimal string")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a valid amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be a finite non-negative amount")
    return amount


def _amount_string(value: Decimal) -> str:
    return format(value, "f")


def outgoing_invoice_message(
    *, invoice_id: str, amount_due: Any, currency: str, message_id: str
) -> dict[str, str]:
    """Create the minimal canonical shape representing an outgoing ``INV`` message."""
    invoice_id, currency, message_id = map(_text, (invoice_id, currency, message_id))
    if not invoice_id or not currency or not message_id:
        raise ValueError("invoice_id, currency and message_id are required")
    return {
        "kind": "INV",
        "invoice_id": invoice_id,
        "amount_due": _amount_string(_amount(amount_due, "amount_due")),
        "currency": currency.upper(),
        "message_id": message_id,
    }


def reconcile_payment(
    invoice_message: Mapping[str, Any],
    payment: Mapping[str, Any],
    *,
    prior_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Classify one payment and emit a non-mutating receipt proposal.

    ``payment`` requires ``payment_id``, ``amount`` and ``currency``.  Matching
    is deliberately fail-closed: an absent/mismatched invoice reference,
    currency mismatch, malformed evidence, or duplicate payment identity is
    blocked as ambiguous/duplicate rather than inferred.
    """
    if _text(invoice_message.get("kind")) != "INV":
        raise ValueError("invoice_message.kind must be INV")
    invoice_id = _text(invoice_message.get("invoice_id"))
    message_id = _text(invoice_message.get("message_id"))
    currency = _text(invoice_message.get("currency")).upper()
    if not invoice_id or not message_id or not currency:
        raise ValueError("invoice message requires invoice_id, message_id and currency")
    due = _amount(invoice_message.get("amount_due"), "amount_due")

    payment_id = _text(payment.get("payment_id"))
    payment_currency = _text(payment.get("currency")).upper()
    if not payment_id or not payment_currency:
        raise ValueError("payment requires payment_id and currency")
    paid = _amount(payment.get("amount"), "payment.amount")
    reference = _text(payment.get("invoice_id") or payment.get("reference"))

    base = {
        "proposal_type": "invoice_payment_receipt",
        "invoice_id": invoice_id,
        "invoice_message_id": message_id,
        "payment_id": payment_id,
        "currency": currency,
        "amount_due": _amount_string(due),
        "amount_received": _amount_string(paid),
        "remaining_amount": _amount_string(max(due - paid, Decimal("0"))),
        "finance_mutation": False,
    }
    prior_payment_ids = {_text(item.get("payment_id")) for item in prior_receipts}
    if payment_id in prior_payment_ids:
        return {**base, "classification": "duplicate", "state": "blocked", "reason": "payment_id_already_proposed"}
    if payment_currency != currency:
        return {**base, "classification": "ambiguous", "state": "blocked", "reason": "currency_mismatch"}
    if reference != invoice_id:
        return {**base, "classification": "ambiguous", "state": "blocked", "reason": "invoice_reference_missing_or_mismatched"}
    if paid == due:
        return {**base, "classification": "exact", "state": "verified", "reason": "exact_amount_and_reference_match"}
    if paid < due:
        return {**base, "classification": "partial", "state": "pending", "reason": "referenced_payment_is_less_than_amount_due"}
    return {**base, "classification": "ambiguous", "state": "blocked", "reason": "payment_exceeds_amount_due"}


# Explicit alias for consumers which prefer a proposal-oriented name.
build_receipt_proposal = reconcile_payment

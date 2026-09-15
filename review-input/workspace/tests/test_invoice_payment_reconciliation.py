from scripts.invoice_payment_reconciliation import (
    build_receipt_proposal,
    outgoing_invoice_message,
    reconcile_payment,
)


def invoice():
    return outgoing_invoice_message(
        invoice_id="INV-2026-0042", amount_due="125.00", currency="gbp", message_id="out-991"
    )


def payment(payment_id="pay-1", amount="125.00", **extra):
    return {"payment_id": payment_id, "amount": amount, "currency": "GBP", "invoice_id": "INV-2026-0042", **extra}


def test_outgoing_inv_message_is_canonical_and_exact():
    assert invoice() == {
        "kind": "INV",
        "invoice_id": "INV-2026-0042",
        "amount_due": "125.00",
        "currency": "GBP",
        "message_id": "out-991",
    }


def test_exact_referenced_payment_emits_verified_receipt_proposal():
    proposal = reconcile_payment(invoice(), payment())
    assert proposal["classification"] == "exact"
    assert proposal["state"] == "verified"
    assert proposal["remaining_amount"] == "0.00"
    assert proposal["finance_mutation"] is False


def test_partial_referenced_payment_emits_pending_receipt_proposal():
    proposal = build_receipt_proposal(invoice(), payment(amount="25.00"))
    assert proposal["classification"] == "partial"
    assert proposal["state"] == "pending"
    assert proposal["remaining_amount"] == "100.00"


def test_seen_payment_id_is_duplicate_and_blocked():
    proposal = reconcile_payment(invoice(), payment(), prior_receipts=[{"payment_id": "pay-1"}])
    assert proposal["classification"] == "duplicate"
    assert proposal["state"] == "blocked"
    assert proposal["reason"] == "payment_id_already_proposed"


def test_missing_or_wrong_invoice_reference_is_ambiguous_and_blocked():
    proposal = reconcile_payment(invoice(), payment(invoice_id="INV-OTHER"))
    assert proposal["classification"] == "ambiguous"
    assert proposal["state"] == "blocked"
    assert proposal["reason"] == "invoice_reference_missing_or_mismatched"


def test_currency_mismatch_is_ambiguous_and_blocked():
    proposal = reconcile_payment(invoice(), payment(currency="USD"))
    assert proposal["classification"] == "ambiguous"
    assert proposal["state"] == "blocked"
    assert proposal["reason"] == "currency_mismatch"

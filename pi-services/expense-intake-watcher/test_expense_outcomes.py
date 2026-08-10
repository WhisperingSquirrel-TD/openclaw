#!/usr/bin/env python3
"""Regression contract for all-mirror expense outcomes."""
from __future__ import annotations

import unittest

from expense_outcomes import build_outcome


class OutcomeContractTests(unittest.TestCase):
    def test_external_only_invoice_can_be_preserved_as_a_bounded_blocker(self) -> None:
        outcome = build_outcome(
            source_id="microsoft-external:HUB-001042",
            source_surface="microsoft_external",
            expense_outcome="blocked",
            canonical_ref="seer-expenses.md#pending:HUB-001042",
            ledger_state="pending",
            evidence_state="blocked",
            blocker="external mirror body hidden; full invoice extraction unavailable",
            candidate_reason="OBCN invoice signal",
            observed_at="2026-08-10T09:00:00Z",
        )
        self.assertEqual(outcome.expense_outcome, "blocked")
        self.assertEqual(outcome.ledger_state, "pending")
        self.assertEqual(outcome.evidence_state, "blocked")

    def test_duplicate_requires_exact_canonical_reference(self) -> None:
        with self.assertRaisesRegex(ValueError, "canonical_ref"):
            build_outcome(
                source_id="email:microsoft:abc",
                source_surface="microsoft_inbox",
                expense_outcome="duplicate",
                canonical_ref=None,
                ledger_state="written",
                evidence_state="retained",
            )

    def test_blocked_requires_exact_blocker(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact blocker"):
            build_outcome(
                source_id="teams:abc",
                source_surface="teams_recent",
                expense_outcome="blocked",
                canonical_ref="seer-expenses.md#pending:teams-abc",
                ledger_state="pending",
                evidence_state="pending",
            )

    def test_not_needed_cannot_claim_expense_completion(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot claim"):
            build_outcome(
                source_id="whatsapp:abc",
                source_surface="whatsapp_recent",
                expense_outcome="not_needed",
                canonical_ref="seer-expenses.md#bad",
                ledger_state="not_required",
                evidence_state="not_required",
            )

    def test_logged_cannot_hide_financial_blocker(self) -> None:
        with self.assertRaisesRegex(ValueError, "blocked ledger"):
            build_outcome(
                source_id="email:assistant:abc",
                source_surface="assistant_inbox",
                expense_outcome="logged",
                canonical_ref="seer-expenses.md#row:abc",
                ledger_state="blocked",
                evidence_state="pending",
            )


if __name__ == "__main__":
    unittest.main()

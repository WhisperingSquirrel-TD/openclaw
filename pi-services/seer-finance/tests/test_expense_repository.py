"""Focused tests for the Phase 1 SQLite expense repository."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from seer_finance.ledger.expense_repository import (
    ExpenseRepository,
    ExpenseRepositoryError,
    ExpenseStatus,
    InvalidTransitionError,
)


class ExpenseRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "expenses.sqlite3"
        self.repo = ExpenseRepository(self.path)

    def tearDown(self) -> None:
        self.repo.close()
        self.tempdir.cleanup()

    def test_exact_capture_replay_is_idempotent(self) -> None:
        capture = dict(
            source_surface="telegram", source_ref="telegram:message:42",
            supplier="Acme", amount_pence=1234, currency="GBP",
        )
        first = self.repo.capture(**capture)
        second = self.repo.capture(**capture)

        self.assertEqual(first, second)
        self.assertEqual(1, self.repo.connection.execute("SELECT count(*) FROM expenses").fetchone()[0])
        self.assertEqual(1, len(self.repo.events(first.expense_id)))
        self.assertEqual([], self.repo.capture_collisions(first.expense_id))

    def test_conflicting_source_capture_preserves_original_and_incoming_facts(self) -> None:
        original = self.repo.capture(
            source_surface="telegram", source_ref="telegram:message:99",
            supplier="Acme", amount_pence=1234, currency="GBP",
        )
        result = self.repo.capture(
            source_surface="telegram", source_ref="telegram:message:99",
            supplier="Different supplier", amount_pence=9999, currency="GBP",
            evidence_ref="telegram://message/99",
        )

        # The canonical record remains intact, but non-conflicting enrichment is retained.
        self.assertEqual(original.expense_id, result.expense_id)
        self.assertEqual("Acme", result.supplier)
        self.assertEqual(1234, result.amount_pence)
        self.assertEqual("telegram://message/99", result.evidence_ref)
        collisions = self.repo.capture_collisions(original.expense_id)
        self.assertEqual(1, len(collisions))
        preserved_original = json.loads(collisions[0]["original_facts_json"])
        preserved_incoming = json.loads(collisions[0]["incoming_facts_json"])
        self.assertEqual("Acme", preserved_original["supplier"])
        self.assertEqual(1234, preserved_original["amount_pence"])
        self.assertEqual("Different supplier", preserved_incoming["supplier"])
        self.assertEqual(9999, preserved_incoming["amount_pence"])
        self.assertEqual("telegram://message/99", preserved_incoming["evidence_ref"])

        # Repeating the same collision is also idempotent rather than multiplying records.
        self.repo.capture(
            source_surface="telegram", source_ref="telegram:message:99",
            supplier="Different supplier", amount_pence=9999, currency="GBP",
            evidence_ref="telegram://message/99",
        )
        self.assertEqual(1, len(self.repo.capture_collisions(original.expense_id)))

    def test_allowed_transition_is_recorded(self) -> None:
        expense = self.repo.capture(source_surface="email", source_ref="email:1")
        confirmed = self.repo.transition(expense.expense_id, ExpenseStatus.CONFIRMED)

        self.assertEqual(ExpenseStatus.CONFIRMED, confirmed.status)
        event = self.repo.events(expense.expense_id)[-1]
        self.assertEqual("transition", event["event_type"])
        self.assertEqual("needs_review", event["from_status"])
        self.assertEqual("confirmed", event["to_status"])
        self.assertEqual("applied", event["outcome"])

    def test_rejected_transition_does_not_change_status_and_is_recorded(self) -> None:
        expense = self.repo.capture(source_surface="email", source_ref="email:2")

        with self.assertRaisesRegex(InvalidTransitionError, "cannot transition needs_review to ledger_written"):
            self.repo.transition(expense.expense_id, ExpenseStatus.LEDGER_WRITTEN)

        self.assertEqual(ExpenseStatus.NEEDS_REVIEW, self.repo.get(expense.expense_id).status)
        event = self.repo.events(expense.expense_id)[-1]
        self.assertEqual("rejected", event["outcome"])
        self.assertEqual("invalid_transition", event["error_code"])

    def test_source_ref_is_unique(self) -> None:
        expense = self.repo.capture(source_surface="whatsapp", source_ref="wa:100")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.connection.execute(
                "INSERT INTO expenses (expense_id, source_surface, source_ref, status, observed_timestamp, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("other-id", "email", expense.source_ref, "needs_review", "now", "now", "now"),
            )

    def test_migration_is_idempotent_and_constraints_are_enforced(self) -> None:
        self.repo.close()
        reopened = ExpenseRepository(self.path)
        self.repo = reopened
        self.assertEqual(
            1, reopened.connection.execute("SELECT count(*) FROM schema_migrations WHERE version = 2").fetchone()[0]
        )
        self.assertEqual(
            1, reopened.connection.execute("SELECT count(*) FROM schema_migrations WHERE version = 3").fetchone()[0]
        )
        with self.assertRaises(sqlite3.IntegrityError):
            reopened.connection.execute(
                "INSERT INTO expenses (expense_id, source_surface, source_ref, status, observed_timestamp, "
                "amount_pence, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("bad-pence", "test", "bad:pence", "needs_review", "now", -1, "now", "now"),
            )

    def test_receipt_evidence_is_linked_by_existing_source_ref(self) -> None:
        expense = self.repo.capture(source_surface="email", source_ref="email:receipt:1")
        digest = "a" * 64

        evidence = self.repo.record_receipt_evidence(
            source_ref=expense.source_ref,
            evidence_kind="receipt_pdf",
            local_path="/var/lib/seer/receipts/1.pdf",
            sha256=digest,
            sharepoint_path="Shared Documents/Receipts/1.pdf",
            sharepoint_url="https://contoso.sharepoint.com/receipt/1",
            sharepoint_etag='"1"',
            source_timestamp="2026-08-14T17:00:00+00:00",
        )

        self.assertEqual(expense.source_ref, evidence.source_ref)
        self.assertEqual("receipt_pdf", evidence.evidence_kind)
        self.assertEqual(digest, evidence.sha256)
        self.assertEqual([evidence], self.repo.receipt_evidence(expense.source_ref))
        self.assertTrue(evidence.created_at)

    def test_receipt_evidence_requires_existing_source_ref_and_valid_sha256(self) -> None:
        with self.assertRaisesRegex(ExpenseRepositoryError, "unknown source_ref"):
            self.repo.record_receipt_evidence(
                source_ref="email:missing", evidence_kind="receipt_pdf"
            )
        self.assertEqual(0, self.repo.connection.execute(
            "SELECT count(*) FROM receipt_evidence"
        ).fetchone()[0])

        expense = self.repo.capture(source_surface="email", source_ref="email:receipt:2")
        for invalid_digest in ("A" * 64, "a" * 63, "g" * 64):
            with self.subTest(invalid_digest=invalid_digest):
                with self.assertRaisesRegex(ValueError, "sha256"):
                    self.repo.record_receipt_evidence(
                        source_ref=expense.source_ref,
                        evidence_kind="receipt_pdf",
                        sha256=invalid_digest,
                    )
        self.assertEqual(0, len(self.repo.receipt_evidence(expense.source_ref)))
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.connection.execute(
                "INSERT INTO receipt_evidence "
                "(evidence_id, source_ref, evidence_kind, sha256, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("bad-sha", expense.source_ref, "receipt_pdf", "A" * 64, "now"),
            )

    def test_receipt_evidence_is_database_immutable(self) -> None:
        expense = self.repo.capture(source_surface="email", source_ref="email:receipt:3")
        evidence = self.repo.record_receipt_evidence(
            source_ref=expense.source_ref, evidence_kind="receipt_image"
        )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "receipt evidence is immutable"):
            self.repo.connection.execute(
                "UPDATE receipt_evidence SET local_path = ? WHERE evidence_id = ?",
                ("/replacement.jpg", evidence.evidence_id),
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "receipt evidence is immutable"):
            self.repo.connection.execute(
                "DELETE FROM receipt_evidence WHERE evidence_id = ?", (evidence.evidence_id,)
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from finance_handoff import (
    FINANCE_LEDGER_PATH,
    TransactionValidationError,
    append_validated_expense,
)
from sharepoint_boundary import BoundaryResult


class FakeBoundary:
    def __init__(self, result: BoundaryResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str, str]] = []

    def write_verified(self, path: str, content: str, *, operation: str = "append") -> BoundaryResult:
        self.calls.append((path, content, operation))
        return self.result

    def read(self, path: str) -> str:
        return ""


class QueueAndCacheBoundary(FakeBoundary):
    """Adversarial boundary: completion requires both transport and readback."""

    def __init__(self) -> None:
        super().__init__(BoundaryResult(
            operation="append",
            path=FINANCE_LEDGER_PATH,
            accepted=True,
            verified=False,
            blocker="queue result/readback pending",
        ))
        self.queue_processed = False
        self.cached_content: str | None = None

    def write_verified(self, path: str, content: str, *, operation: str = "append") -> BoundaryResult:
        self.calls.append((path, content, operation))
        verified = self.queue_processed and self.cached_content == content
        return BoundaryResult(
            operation=operation,
            path=path,
            accepted=True,
            verified=verified,
            canonical_ref="sharepoint:finance-test" if verified else None,
            blocker=None if verified else "queue result/readback pending",
        )


class FinanceHandoffTests(unittest.TestCase):
    def candidate(self) -> dict:
        return {
            "txn_id": "expense-test-1",
            "date": "2026-08-10",
            "direction": "expense",
            "amount_pence": 42,
            "description": "Microsoft billing",
            "counterparty": "Microsoft",
            "category": "software",
            "source_ref": "microsoft:G175174660",
        }

    def test_requires_verified_readback_from_canonical_finance_document(self) -> None:
        boundary = FakeBoundary(BoundaryResult(
            operation="append",
            path=FINANCE_LEDGER_PATH,
            accepted=True,
            verified=True,
        ))
        result = append_validated_expense(boundary, self.candidate())
        self.assertTrue(result.complete)
        self.assertEqual(
            result.canonical_ref,
            "/Finance/Finance ledger.md#source_ref:microsoft:G175174660",
        )
        self.assertEqual(boundary.calls[0][0], FINANCE_LEDGER_PATH)

    def test_queued_write_is_not_claimed_as_finance_completion(self) -> None:
        boundary = FakeBoundary(BoundaryResult(
            operation="append",
            path=FINANCE_LEDGER_PATH,
            accepted=True,
            verified=False,
            blocker="verified readback pending",
        ))
        result = append_validated_expense(boundary, self.candidate())
        self.assertFalse(result.complete)
        self.assertIsNone(result.canonical_ref)

    def test_refuses_incomplete_financial_data_without_local_fallback(self) -> None:
        boundary = FakeBoundary(BoundaryResult(
            operation="append",
            path=FINANCE_LEDGER_PATH,
            accepted=False,
            verified=False,
            blocker="not called",
        ))
        bad = self.candidate()
        bad.pop("category")
        with self.assertRaises(TransactionValidationError):
            append_validated_expense(boundary, bad)
        self.assertFalse(boundary.calls)

    def test_completion_requires_queue_result_and_exact_cache_version(self) -> None:
        boundary = QueueAndCacheBoundary()
        first = append_validated_expense(boundary, self.candidate())
        self.assertFalse(first.complete)
        self.assertIsNone(first.canonical_ref)

        content = boundary.calls[-1][1]
        boundary.queue_processed = True
        boundary.cached_content = content + "stale"
        stale = append_validated_expense(boundary, self.candidate())
        self.assertFalse(stale.complete)
        self.assertIsNone(stale.canonical_ref)

        boundary.cached_content = content
        verified = append_validated_expense(boundary, self.candidate())
        self.assertTrue(verified.complete)
        self.assertEqual("sharepoint:finance-test", verified.canonical_ref)


if __name__ == "__main__":
    unittest.main()
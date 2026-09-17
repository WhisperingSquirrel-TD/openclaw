import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from seer_finance.agent_expense_bridge import handle
from seer_finance.ledger.sharepoint_contract import (
    SharePointMutationBlocked,
    SharePointRebaseRequired,
    SharePointWritePending,
)
from seer_finance.ledger.sharepoint_repository import CaptureCollisionPending
from seer_finance.ledger.workbook_codec import WorkbookCodec
from seer_finance.sharepoint_boundary import BoundaryResult


class _Boundary:
    def __init__(self, *, receipt_result=None, workbook_result=None):
        self.receipt_result = receipt_result
        self.workbook_result = workbook_result
        self.receipt_calls = []
        self.workbook_calls = []

    def read_workbook_snapshot(self, path):
        self.read_path = path
        return {
            "content_bytes": WorkbookCodec.encode_expense({
                "schema_version": 1,
                "expenses": [{
                    "expense_id": "expense-1",
                    "source_ref": "whatsapp:lidl-1",
                    "status": "needs_review",
                    "supplier": "Lidl",
                    "amount_pence": 4218,
                }, {
                    "expense_id": "expense-2",
                    "source_ref": "whatsapp:other-2",
                    "status": "confirmed",
                }],
                "evidence": [{
                    "evidence_id": "evidence-1",
                    "source_ref": "whatsapp:lidl-1",
                    "evidence_kind": "receipt",
                    "sharepoint_path": "/Expenses/Meals & Refreshments/example.jpg",
                }],
                "events": [{
                    "event_id": "event-1",
                    "expense_id": "expense-1",
                    "event_type": "capture",
                    "to_status": "needs_review",
                    "outcome": "applied",
                }],
                "collisions": [],
            }),
            "content_sha256": "a" * 64,
            "semantic_workbook_sha256": "b" * 64,
            "etag": '"etag-1"',
            "version": '"version-1"',
        }

    def upload_receipt_verified(self, **kwargs):
        self.receipt_calls.append(kwargs)
        return self.receipt_result

    def write_workbook_verified(self, path, content_base64, **kwargs):
        self.workbook_calls.append((path, content_base64, kwargs))
        return self.workbook_result


class _Repository:
    def __init__(self, result=None, error=None, collisions=None):
        self.result = result
        self.error = error
        self.collisions = collisions or []
        self.calls = []

    def capture(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result

    def capture_collisions(self, expense_id):
        return self.collisions


class _Expense:
    expense_id = "expense-1"
    source_surface = "owner_chat"
    source_ref = "whatsapp:lidl-1"
    status = "needs_review"
    source_timestamp = "2026-09-16T09:00:00Z"
    observed_timestamp = "2026-09-16T09:01:00Z"
    supplier = "Lidl"
    amount_pence = 4218
    currency = "EUR"
    expense_date = "2026-09-16"
    category = "groceries"
    evidence_ref = "receipt-1"
    evidence_state = "uploaded"
    settlement_state = "company_card"
    finance_ledger_ref = "ledger-1"
    validation_result = "matched"


class AgentExpenseBridgeTests(unittest.TestCase):
    def test_read_is_fixed_to_the_canonical_expense_workbook(self):
        boundary = _Boundary()
        result = handle(
            {"action": "read_expense_workbook", "page": 0, "page_size": 1},
            boundary=boundary,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(boundary.read_path, "/Expenses/Expense ledger.xlsx")
        self.assertEqual(result["metadata"]["etag"], '"etag-1"')
        self.assertEqual(2, result["metadata"]["total_expenses"])
        self.assertEqual(1, len(result["rows"]))
        self.assertEqual("Lidl", result["rows"][0]["supplier"])
        self.assertEqual(1, len(result["evidence"]))
        self.assertEqual(1, len(result["status_events"]))
        self.assertEqual("Meals & Refreshments", result["metadata"]["approved_receipt_folders"][2])
        self.assertNotIn("content_base64", result)
        self.assertNotIn("content_bytes", result)

    def test_receipt_upload_accepts_only_inbound_media_and_preserves_pending_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / "custom-profile"
            media = state_dir / "media" / "inbound"
            media.mkdir(parents=True)
            receipt = media / "lidl.jpg"
            content = b"receipt image bytes"
            receipt.write_bytes(content)
            old_state_dir = os.environ.get("OPENCLAW_STATE_DIR")
            old_media_root = os.environ.pop("SEER_FINANCE_EXPENSE_MEDIA_ROOT", None)
            os.environ["OPENCLAW_STATE_DIR"] = str(state_dir)
            try:
                boundary = _Boundary(receipt_result=BoundaryResult(
                    operation="upload_binary", path="/Expenses/Meals & Refreshments/lidl.jpg",
                    accepted=True, verified=False, blocker="queued",
                ))
                result = handle({
                    "action": "upload_expense_receipt",
                    "source_ref": "whatsapp:lidl-1",
                    "receipt_media_path": str(receipt),
                    "receipt_folder": "Meals & Refreshments",
                }, boundary=boundary)
            finally:
                if old_state_dir is None:
                    os.environ.pop("OPENCLAW_STATE_DIR", None)
                else:
                    os.environ["OPENCLAW_STATE_DIR"] = old_state_dir
                if old_media_root is not None:
                    os.environ["SEER_FINANCE_EXPENSE_MEDIA_ROOT"] = old_media_root

        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["complete"])
        expected_hash = hashlib.sha256(content).hexdigest()
        self.assertEqual(boundary.receipt_calls[0]["content_sha256"], expected_hash)
        self.assertEqual(boundary.receipt_calls[0]["mime_type"], "image/jpeg")
        self.assertEqual(
            boundary.receipt_calls[0]["path"],
            f"/Expenses/Meals & Refreshments/{expected_hash}.jpg",
        )

    def test_receipt_upload_rejects_non_media_path_without_calling_boundary(self):
        boundary = _Boundary()
        result = handle({
            "action": "upload_expense_receipt",
            "source_ref": "receipt-1",
            "receipt_media_path": "/etc/shadow",
            "receipt_folder": "Receipts",
        }, boundary=boundary)

        self.assertFalse(result["ok"])
        self.assertIn("inbound media", result["error"])
        self.assertEqual(boundary.receipt_calls, [])

    def test_receipt_upload_rejects_agent_supplied_hash_or_destination_fields(self):
        boundary = _Boundary()
        result = handle({
            "action": "upload_expense_receipt",
            "source_ref": "receipt-1",
            "receipt_media_path": "/not-used",
            "receipt_folder": "Receipts",
            "content_sha256": "a" * 64,
        }, boundary=boundary)

        self.assertFalse(result["ok"])
        self.assertIn("unsupported field", result["error"])
        self.assertEqual(boundary.receipt_calls, [])

    def test_receipt_upload_uses_each_approved_existing_expenses_folder(self):
        approved_folders = (
            "Anthropic", "ChatGPT", "Meals & Refreshments", "Not organised",
            "OpenAI API", "Receipts", "Replit", "SEER",
        )
        with tempfile.TemporaryDirectory() as temporary:
            media_root = Path(temporary) / "media" / "inbound"
            media_root.mkdir(parents=True)
            receipt = media_root / "receipt.png"
            receipt.write_bytes(b"original receipt bytes")
            old_media_root = os.environ.get("SEER_FINANCE_EXPENSE_MEDIA_ROOT")
            os.environ["SEER_FINANCE_EXPENSE_MEDIA_ROOT"] = str(media_root)
            try:
                expected_hash = hashlib.sha256(receipt.read_bytes()).hexdigest()
                for folder in approved_folders:
                    boundary = _Boundary(receipt_result=BoundaryResult(
                        operation="upload_binary", path="/unused", accepted=True, verified=True,
                    ))
                    result = handle({
                        "action": "upload_expense_receipt",
                        "source_ref": "whatsapp:receipt-1",
                        "receipt_media_path": str(receipt),
                        "receipt_folder": folder,
                    }, boundary=boundary)
                    self.assertTrue(result["ok"], folder)
                    self.assertEqual(
                        boundary.receipt_calls[0]["path"],
                        f"/Expenses/{folder}/{expected_hash}.png",
                    )
            finally:
                if old_media_root is None:
                    os.environ.pop("SEER_FINANCE_EXPENSE_MEDIA_ROOT", None)
                else:
                    os.environ["SEER_FINANCE_EXPENSE_MEDIA_ROOT"] = old_media_root

    def test_receipt_upload_rejects_unapproved_or_path_like_folder_values(self):
        boundary = _Boundary()
        for receipt_folder in (
            "../Receipts", "Receipts/2026", "Receipts%2F2026",
            "Meals & Refreshments/..", "Receipt evidence", "",
        ):
            result = handle({
                "action": "upload_expense_receipt",
                "source_ref": "receipt-1",
                "receipt_media_path": "/not-used",
                "receipt_folder": receipt_folder,
            }, boundary=boundary)
            self.assertFalse(result["ok"], receipt_folder)
            self.assertIn("receipt_folder", result["error"])
        self.assertEqual(boundary.receipt_calls, [])

    def test_raw_workbook_write_is_not_an_approved_agent_operation(self):
        boundary = _Boundary()
        result = handle({"action": "write_expense_workbook"}, boundary=boundary)

        self.assertFalse(result["ok"])
        self.assertIn("not an approved", result["error"])
        self.assertEqual(boundary.workbook_calls, [])

    def test_source_linked_capture_uses_repository_merge_and_marks_queue_pending(self):
        repository = _Repository(error=SharePointWritePending("queued readback"))
        result = handle({
            "action": "capture_expense",
            "source_ref": "whatsapp:lidl-1",
            "facts": {
                "supplier": "Lidl", "amount_pence": 4218, "currency": "EUR",
                "settlement_state": "company_card",
            },
        }, repository=repository)

        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["complete"])
        self.assertEqual("owner_chat", repository.calls[0]["source_surface"])
        self.assertEqual("whatsapp:lidl-1", repository.calls[0]["source_ref"])

    def test_capture_is_complete_only_for_a_matching_collision_free_readback(self):
        repository = _Repository(result=_Expense())
        result = handle({
            "action": "capture_expense",
            "source_ref": "whatsapp:lidl-1",
            "facts": {
                "source_timestamp": "2026-09-16T09:00:00Z",
                "observed_timestamp": "2026-09-16T09:01:00Z",
                "supplier": "Lidl",
                "amount_pence": 4218,
                "currency": "EUR",
                "finance_ledger_ref": "ledger-1",
            },
        }, repository=repository)

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["complete"])
        self.assertEqual("2026-09-16T09:01:00Z", result["result"]["expense"]["observed_timestamp"])
        self.assertEqual("ledger-1", result["result"]["expense"]["finance_ledger_ref"])

    def test_capture_rejects_unresolved_collisions_or_nonmatching_readback(self):
        conflicting = handle({
            "action": "capture_expense",
            "source_ref": "whatsapp:lidl-1",
            "facts": {"supplier": "Lidl"},
        }, repository=_Repository(result=_Expense(), collisions=[{"collision_id": "collision-1"}]))
        mismatched = handle({
            "action": "capture_expense",
            "source_ref": "whatsapp:lidl-1",
            "facts": {"supplier": "Different supplier"},
        }, repository=_Repository(result=_Expense()))

        for result in (conflicting, mismatched):
            self.assertFalse(result["ok"])
            self.assertFalse(result["result"]["accepted"])
            self.assertFalse(result["result"]["complete"])

    def test_capture_rejects_unsupported_facts_before_repository_call(self):
        repository = _Repository(result=_Expense())
        result = handle({
            "action": "capture_expense",
            "source_ref": "whatsapp:lidl-1",
            "facts": {"line_items": ["unsupported schema"]},
        }, repository=repository)

        self.assertFalse(result["ok"])
        self.assertIn("unknown expense fact", result["error"])
        self.assertEqual([], repository.calls)

    def test_capture_does_not_accept_blocked_rebased_or_conflicting_pending_writes(self):
        request = {
            "action": "capture_expense",
            "source_ref": "whatsapp:lidl-1",
            "facts": {"supplier": "Lidl"},
        }
        for error in (
            SharePointMutationBlocked("blocked mutation"),
            SharePointRebaseRequired("rebase required"),
            CaptureCollisionPending("conflict queued for review"),
        ):
            result = handle(request, repository=_Repository(error=error))
            self.assertFalse(result["ok"])
            self.assertFalse(result["result"]["accepted"])
            self.assertFalse(result["result"]["complete"])

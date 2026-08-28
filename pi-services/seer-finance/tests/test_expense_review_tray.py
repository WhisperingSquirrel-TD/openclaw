"""Focused safety tests for the read-only expense review snapshot."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from seer_finance.ledger.expense_review_tray import build_review_snapshot, review_snapshot_is_current


class ExpenseReviewTrayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.manifest_path = self.root / "manifest.json"
        self.manifest = {
            "manifest_version": 2,
            "inputs": {"transactions_json": {"path": "/read-only/transactions.json", "sha256": "a" * 64}, "seer_expenses_markdown": {"path": "/read-only/seer-expenses.md", "sha256": "b" * 64}},
            "records": [
                {"source": "transactions_json", "source_location": "$[4]", "classification": "imported_candidate", "original_source_ref": "txn:ready", "original": {"amount_pence": 100}, "candidate": {"source_ref": "txn:ready", "proposed_status": "ledger_written"}},
                {"source": "seer_expenses_markdown", "source_location": "line:9", "classification": "imported_candidate", "original_source_ref": "note:review", "original": {"raw": "unknown expense"}, "candidate": {"source_ref": "note:review", "proposed_status": "needs_review"}},
                {"source": "seer_expenses_markdown", "source_location": "line:10", "classification": "preserved_for_review", "original": {"raw": "TBC"}, "reason": "no stable source reference extractable"},
                {"source": "transactions_json", "source_location": "$[7]", "classification": "preserved_for_review", "original_source_ref": "legacy:dup", "original": {"txn_id": "one"}, "reason": "repeated legacy source_ref"},
                {"source": "transactions_json", "source_location": "$[8]", "classification": "preserved_for_review", "original_source_ref": "legacy:dup", "original": {"txn_id": "two"}, "reason": "repeated legacy source_ref"},
                {"source": "expense_enrichment_queue", "source_location": "$.items[0]", "classification": "not_needed", "original_source_ref": "telegram:rectified:1", "original": {"state": "not_needed"}, "reason": "queue item was explicitly rectified/closed as not-needed; retained for audit only", "candidate": {"proposed_status": "not_needed"}},
            ],
        }
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_deterministic_review_identity_uses_source_location_and_checksum(self) -> None:
        first = build_review_snapshot(self.manifest)
        second = build_review_snapshot(copy.deepcopy(self.manifest))
        self.assertEqual(first["stale_review_protection"], second["stale_review_protection"])
        self.assertEqual([item["review_id"] for item in first["queues"]["evidence_supported_ready_to_validate"]], [item["review_id"] for item in second["queues"]["evidence_supported_ready_to_validate"]])
        changed = copy.deepcopy(self.manifest)
        changed["inputs"]["transactions_json"]["sha256"] = "c" * 64
        self.assertNotEqual(first["queues"]["evidence_supported_ready_to_validate"][0]["review_id"], build_review_snapshot(changed)["queues"]["evidence_supported_ready_to_validate"][0]["review_id"])

    def test_category_grouping_and_prompts_are_explicit_only_when_needed(self) -> None:
        snapshot = build_review_snapshot(self.manifest)
        queues = snapshot["queues"]
        self.assertEqual("txn:ready", queues["evidence_supported_ready_to_validate"][0]["original_source_ref"])
        review = next(item for item in queues["needs_decision"] if item["original_source_ref"] == "note:review")
        self.assertEqual(2, len(review["review_prompts"]))
        self.assertEqual([], queues["evidence_supported_ready_to_validate"][0]["review_prompts"])
        self.assertEqual(1, len(queues["evidence_gap"]))
        self.assertIn("missing/ambiguous", queues["evidence_gap"][0]["review_prompts"][0])

    def test_not_needed_records_are_retained_as_audit_but_excluded_from_review_queues(self) -> None:
        snapshot = build_review_snapshot(self.manifest)
        self.assertTrue(all(item["original_source_ref"] != "telegram:rectified:1" for queue in snapshot["queues"].values() for item in queue))
        self.assertEqual(["telegram:rectified:1"], [item["original_source_ref"] for item in snapshot["excluded_not_needed_audit"]])

    def test_duplicate_cluster_preserves_all_original_locations_and_payloads(self) -> None:
        snapshot = build_review_snapshot(self.manifest)
        self.assertEqual(1, len(snapshot["duplicate_conflict_clusters"]))
        cluster = snapshot["duplicate_conflict_clusters"][0]
        self.assertEqual("legacy:dup", cluster["source_reference"])
        self.assertEqual(["/read-only/transactions.json", "/read-only/transactions.json"], [member["source_path"] for member in cluster["members"]])
        self.assertEqual(["$[7]", "$[8]"], [member["source_location"] for member in cluster["members"]])
        self.assertEqual(["one", "two"], [member["retained_payload"]["txn_id"] for member in cluster["members"]])
        self.assertEqual(2, len([item for item in snapshot["queues"]["needs_decision"] if item["original_source_ref"] == "legacy:dup"]))

    def test_stale_manifest_identity_detection(self) -> None:
        snapshot = build_review_snapshot(self.manifest_path)
        self.assertTrue(review_snapshot_is_current(snapshot, self.manifest_path))
        stale = copy.deepcopy(self.manifest)
        stale["records"][0]["original"]["amount_pence"] = 101
        self.assertFalse(review_snapshot_is_current(snapshot, stale))

    def test_source_manifest_is_not_mutated(self) -> None:
        before_bytes = self.manifest_path.read_bytes()
        before_object = copy.deepcopy(self.manifest)
        build_review_snapshot(self.manifest)
        build_review_snapshot(self.manifest_path)
        self.assertEqual(before_object, self.manifest)
        self.assertEqual(before_bytes, self.manifest_path.read_bytes())
        self.assertEqual(hashlib.sha256(before_bytes).hexdigest(), hashlib.sha256(self.manifest_path.read_bytes()).hexdigest())

    def test_cli_refuses_destructive_flags_and_existing_output(self) -> None:
        output = self.root / "new" / "snapshot.json"
        command = [sys.executable, "-m", "seer_finance.ledger.expense_review_cli", "--manifest", str(self.manifest_path), "--output", str(output)]
        refused = subprocess.run(command + ["--apply"], capture_output=True, text=True, check=False)
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("refused", refused.stderr)
        created = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(0, created.returncode, created.stderr)
        existing = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertNotEqual(0, existing.returncode)
        self.assertIn("new review snapshot", existing.stderr)


if __name__ == "__main__":
    unittest.main()

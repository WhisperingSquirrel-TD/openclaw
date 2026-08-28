"""Focused tests for the Phase 2 non-destructive expense manifest."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from seer_finance.ledger.expense_importer import build_manifest


class ExpenseImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.transactions = self.root / "transactions.json"
        self.markdown = self.root / "seer-expenses.md"
        self.queue = self.root / "expense-enrichment-queue.json"
        self.tide = self.root / "tide-reconciliation.md"
        self.transactions.write_text(json.dumps([
            {"txn_id": "one", "source_ref": "invoice-INV-1000", "amount_pence": 100},
            {"txn_id": "invoice-receipt", "source_ref": "invoice-INV-070", "amount_pence": 80000}, 
            {"txn_id": "two", "source_ref": "legacy:duplicate", "amount_pence": 200},
            {"txn_id": "three", "source_ref": "legacy:duplicate", "amount_pence": 300},
        ]), encoding="utf-8")
        self.markdown.write_text("""# Supporting log
## Software
| Date | Item | Supplier | Amount | Notes |
|---|---|---|---|---|
| 1 Aug 2026 | Subscription | Acme | £1.00 | Invoice INV-1000 paid |
| TBC | Mystery spend | TBC | TBC | Need more detail |
""", encoding="utf-8")
        self.queue.write_text(json.dumps({"schema_version": 1, "items": [{
            "source_id": "telegram:message:42", "source_surface": "telegram", "state": "needs_enrichment",
            "canonical_ref": "seer-expenses.md#pending:42", "source_excerpt": "£12 unknown supplier"
        }]}), encoding="utf-8")
        self.tide.write_text("""# Tide business-account reconciliation — March to July 2026
## Incoming payments matched to invoice tracker
| Invoice | Client | Amount | Tide statement evidence | Reconciliation |
|---|---|---:|---|---|
| INV-070 | Croyde Medical | £800.00 | 21 Apr — CROYDE MEDIC | Matched receipt; tracker shows Paid |
## Expense/payment reconciliation
All visible card outgoings were reconciled into the supporting ledger.
This named supplier narrative does not identify an individual transaction.
## Applied classification tags
- `TIDE_OWNER_SELF_PAY`: all payments to Thomas Dean/Tom are owner/self-pay movements.
""", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_manifest_preserves_sources_and_reports_checksums_and_counts(self) -> None:
        before = {path: path.read_bytes() for path in (self.transactions, self.markdown, self.queue)}
        manifest = build_manifest(self.transactions, self.markdown, self.queue)
        self.assertEqual("dry_run", manifest["mode"])
        self.assertIn("no database", manifest["no_write_declaration"])
        self.assertEqual("handoff_required_later_live_runtime_phase", manifest["backup_requirements"]["status"])
        self.assertIn("SQLite-consistent", manifest["backup_requirements"]["snapshot_consistency"])
        self.assertIn("source-watermark", manifest["backup_requirements"]["required_manifest"])
        self.assertIn("fail closed", manifest["backup_requirements"]["health_requirement"])
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertEqual(hashlib.sha256(before[self.transactions]).hexdigest(), manifest["inputs"]["transactions_json"]["sha256"])
        self.assertEqual(4, manifest["per_source"]["transactions_json"]["input_items"])
        self.assertNotIn("tide_reconciliation", manifest["inputs"])
        self.assertEqual(2, manifest["per_source"]["transactions_json"]["classifications"]["preserved_for_review"])
        duplicate_rows = [r for r in manifest["records"] if r["original_source_ref"] == "legacy:duplicate"]
        self.assertEqual(["two", "three"], [r["original"]["txn_id"] for r in duplicate_rows])
        ambiguous = next(r for r in manifest["records"] if r["source_location"] == "line:6")
        self.assertEqual("preserved_for_review", ambiguous["classification"])
        self.assertIn("no stable", ambiguous["reason"])
        queue = next(r for r in manifest["records"] if r["source"] == "expense_enrichment_queue")
        self.assertEqual("telegram:message:42", queue["original_source_ref"])
        self.assertEqual("£12 unknown supplier", queue["candidate"]["source_excerpt"])
        self.assertEqual(manifest["totals"]["input_items"], len(manifest["records"]))

    def test_closed_not_needed_queue_item_is_retained_but_not_imported_as_unresolved(self) -> None:
        self.queue.write_text(json.dumps({"schema_version": 1, "items": [{
            "source_id": "telegram:rectified:1", "source_surface": "telegram_inbound", "state": "not_needed",
            "canonical_ref": "seer-expenses.md#pending:rectified:1", "source_excerpt": "expense systems status",
        }]}), encoding="utf-8")
        manifest = build_manifest(self.transactions, self.markdown, self.queue)
        item = next(record for record in manifest["records"] if record["source"] == "expense_enrichment_queue")
        self.assertEqual("not_needed", item["classification"])
        self.assertEqual("not_needed", item["candidate"]["proposed_status"])
        self.assertIn("retained for audit", item["reason"])

    def test_tide_evidence_is_retained_and_never_applied(self) -> None:
        before = {path: path.read_bytes() for path in (self.transactions, self.markdown, self.queue, self.tide)}
        manifest = build_manifest(self.transactions, self.markdown, self.queue, self.tide)
        self.assertEqual(hashlib.sha256(before[self.tide]).hexdigest(), manifest["inputs"]["tide_reconciliation"]["sha256"])
        invoice = next(r for r in manifest["records"] if r["source"] == "tide_reconciliation" and r["original_source_ref"] == "INV-070")
        self.assertEqual("evidence_supported", invoice["classification"])
        self.assertEqual("line:5", invoice["source_location"])
        self.assertEqual("invoice-INV-070", invoice["candidate"]["supports_existing_candidate_ref"])
        self.assertEqual("not_posted", invoice["candidate"]["posting_status"])
        rule = next(r for r in manifest["records"] if r["original_source_ref"] == "TIDE_OWNER_SELF_PAY")
        self.assertEqual("confirmed_classification_rule", rule["classification"])
        self.assertEqual("manual_review_required", rule["candidate"]["application"])
        narrative = next(r for r in manifest["records"] if r["source"] == "tide_reconciliation" and "does not identify" in r["original"]["raw"])
        self.assertEqual("preserved_for_review", narrative["classification"])
        self.assertIn("no individual transaction inferred", narrative["reason"])
        self.assertEqual(1, manifest["summary"]["evidence_supported_existing_candidates"])
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_cli_writes_only_report_and_refuses_cutover(self) -> None:
        output = self.root / "out" / "manifest.json"
        before = {path: path.read_bytes() for path in (self.transactions, self.markdown, self.queue)}
        command = [sys.executable, "-m", "seer_finance.ledger.expense_import_cli", "--transactions", str(self.transactions), "--expenses-markdown", str(self.markdown), "--queue", str(self.queue), "--output", str(output)]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(output.exists())
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        refused = subprocess.run(command + ["--cutover"], capture_output=True, text=True, check=False)
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("refused", refused.stderr)


if __name__ == "__main__":
    unittest.main()

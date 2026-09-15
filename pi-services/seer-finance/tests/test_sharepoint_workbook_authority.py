from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from seer_finance.ledger.sharepoint_contract import (
    FINANCE_LEDGER_PATH,
    SharePointDocumentStore,
    SharePointWritePending,
)
from seer_finance.ledger.workbook_codec import WorkbookCodec, encode_finance_workbook
from openpyxl import load_workbook
from io import BytesIO


class SharePointWorkbookAuthorityTests(unittest.TestCase):
    def test_queue_contains_exact_binary_and_base_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            initial = encode_finance_workbook({"schema_version": 1, "transactions": []})
            desired = encode_finance_workbook({
                "schema_version": 1,
                "transactions": [{"txn_id": "t-1", "amount_pence": 1200}],
            })
            self._cache(cache, initial, etag="e0", version="v0")
            store = SharePointDocumentStore(
                queue_path=root / "queue.json",
                results_path=root / "results.json",
                cache_root=cache,
            )
            with self.assertRaises(SharePointWritePending):
                store.write_workbook(
                    path=FINANCE_LEDGER_PATH,
                    content_base64=base64.b64encode(desired).decode("ascii"),
                    content_sha256=hashlib.sha256(desired).hexdigest(),
                    base_etag="e0",
                    expected_source_sha256=hashlib.sha256(initial).hexdigest(),
                )
            operation = json.loads((root / "queue.json").read_text())[0]
            self.assertEqual("update_workbook", operation["operation"])
            self.assertEqual(
                hashlib.sha256(desired).hexdigest(), operation["content_sha256"]
            )
            self.assertEqual(
                hashlib.sha256(initial).hexdigest(), operation["expected_source_sha256"]
            )
            self.assertEqual(
                WorkbookCodec.semantic_hash(desired), operation["semantic_sha256"]
            )
            self.assertNotIn("content", operation)

    def test_expected_snapshot_is_not_replaced_after_cache_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            initial = encode_finance_workbook({
                "schema_version": 1,
                "transactions": [{"txn_id": "t-1", "amount_pence": 1}],
            })
            desired = encode_finance_workbook({
                "schema_version": 1,
                "transactions": [{"txn_id": "t-1", "amount_pence": 2}],
            })
            self._cache(cache, initial, etag="e0", version="v0")
            store = SharePointDocumentStore(
                queue_path=root / "queue.json",
                results_path=root / "results.json",
                cache_root=cache,
            )
            expected = store.read_workbook_snapshot(FINANCE_LEDGER_PATH)
            # A human edit arrives after the repository decoded expected.
            human = encode_finance_workbook({
                "schema_version": 1,
                "transactions": [{"txn_id": "t-1", "amount_pence": 99}],
            })
            self._cache(cache, human, etag="human", version="v-human")
            with self.assertRaises(SharePointWritePending):
                store.write_workbook(
                    path=FINANCE_LEDGER_PATH,
                    content_base64=base64.b64encode(desired).decode("ascii"),
                    content_sha256=hashlib.sha256(desired).hexdigest(),
                    base_etag=expected["etag"],
                    expected_source_sha256=expected["content_sha256"],
                    expected_snapshot=expected,
                    semantic_workbook_sha256=WorkbookCodec.semantic_hash(desired),
                )
            operation = json.loads((root / "queue.json").read_text())[0]
            self.assertEqual("e0", operation["base_etag"])
            self.assertEqual(expected["content_sha256"], operation["expected_source_sha256"])

    def test_semantic_retry_is_a_verified_noop_without_queueing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            initial = encode_finance_workbook({
                "schema_version": 1,
                "transactions": [{"txn_id": "t-1", "amount_pence": 1}],
            })
            self._cache(cache, initial, etag="e0", version="v0")
            workbook = load_workbook(BytesIO(initial))
            workbook.properties.modified = datetime(2027, 1, 1)
            rewritten = BytesIO()
            workbook.save(rewritten)
            desired = rewritten.getvalue()
            store = SharePointDocumentStore(
                queue_path=root / "queue.json",
                results_path=root / "results.json",
                cache_root=cache,
            )
            expected = store.read_workbook_snapshot(FINANCE_LEDGER_PATH)
            operation_id = store.write_workbook(
                path=FINANCE_LEDGER_PATH,
                content_base64=base64.b64encode(desired).decode("ascii"),
                content_sha256=hashlib.sha256(desired).hexdigest(),
                base_etag=expected["etag"],
                expected_source_sha256=expected["content_sha256"],
                expected_snapshot=expected,
                semantic_workbook_sha256=WorkbookCodec.semantic_hash(desired),
            )
            self.assertFalse((root / "queue.json").exists())
            journal = store._read_journal()
            self.assertEqual(operation_id, journal[0]["id"])
            self.assertTrue(journal[0]["no_op"])
            self.assertEqual(
                operation_id,
                store.write_workbook(
                    path=FINANCE_LEDGER_PATH,
                    content_base64=base64.b64encode(desired).decode("ascii"),
                    content_sha256=hashlib.sha256(desired).hexdigest(),
                    base_etag=expected["etag"],
                    expected_source_sha256=expected["content_sha256"],
                    expected_snapshot=expected,
                    semantic_workbook_sha256=WorkbookCodec.semantic_hash(desired),
                ),
            )
            self.assertFalse((root / "queue.json").exists())

    @staticmethod
    def _cache(cache: Path, content: bytes, *, etag: str, version: str) -> None:
        target = cache / "Finance" / "Finance ledger.xlsx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        digest = hashlib.sha256(content).hexdigest()
        semantic = WorkbookCodec.semantic_hash(content)
        (cache / ".manifest.json").write_text(json.dumps({
            "cached": {
                "Finance/Finance ledger.xlsx": {
                    "sp_path": FINANCE_LEDGER_PATH,
                    "etag": etag,
                    "version": version,
                    "synced_at": now,
                    "content_sha256": digest,
                    "semantic_sha256": semantic,
                }
            }
        }))


if __name__ == "__main__":
    unittest.main()

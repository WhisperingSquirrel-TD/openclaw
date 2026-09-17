#!/usr/bin/env python3
import importlib.util
import hashlib
import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).parent


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


queue_processor = load_module("sharepoint_queue_processor", "sharepoint_queue_processor.py")
sharepoint = load_module("sharepoint", "sharepoint.py")


class Response:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {}
        self.text = content.decode("utf-8", errors="replace") if content else ""

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class QueueSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.old = {
            "QUEUE_FILE": queue_processor.QUEUE_FILE,
            "LOCK_FILE": queue_processor.LOCK_FILE,
            "RESULT_JSON": queue_processor.RESULT_JSON,
            "RESULT_MD": queue_processor.RESULT_MD,
            "LOG_FILE": queue_processor.LOG_FILE,
            "WORKSPACE": queue_processor.WORKSPACE,
            "SP_SCRIPT": queue_processor.SP_SCRIPT,
        }
        queue_processor.QUEUE_FILE = root / "queue.json"
        queue_processor.LOCK_FILE = root / "queue.lock"
        queue_processor.RESULT_JSON = root / "results.json"
        queue_processor.RESULT_MD = root / "results.md"
        queue_processor.LOG_FILE = root / "queue.log"
        queue_processor.WORKSPACE = root / "workspace"
        queue_processor.SP_SCRIPT = root / "sharepoint.py"
        queue_processor.SP_SCRIPT.write_text("# test fixture")

    def tearDown(self):
        for name, value in self.old.items():
            setattr(queue_processor, name, value)
        self.tempdir.cleanup()

    def test_concurrent_producers_do_not_lose_entries(self):
        entries = [
            {"id": f"producer-{index}", "operation": "append",
             "path": f"/Finance/{index}.md", "content": "x"}
            for index in range(32)
        ]
        errors = []

        def produce(entry):
            try:
                self.assertTrue(queue_processor.enqueue_operation(entry))
            except Exception as exc:  # preserve the useful failure in unittest
                errors.append(exc)

        threads = [threading.Thread(target=produce, args=(entry,)) for entry in entries]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertFalse(errors)
        queued = queue_processor._read_queue()
        self.assertEqual({entry["id"] for entry in queued},
                         {entry["id"] for entry in entries})
        self.assertEqual(queue_processor.QUEUE_FILE.stat().st_mode & 0o777, 0o600)

    def test_queue_rewrites_remain_private_even_with_wide_umask(self):
        queue_processor.QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        previous_umask = os.umask(0)
        try:
            queue_processor._write_queue([{"id": "private", "operation": "append"}])
        finally:
            os.umask(previous_umask)
        self.assertEqual(queue_processor.QUEUE_FILE.stat().st_mode & 0o777, 0o600)
        queue_processor._clear_queue()
        self.assertEqual(queue_processor.QUEUE_FILE.stat().st_mode & 0o777, 0o600)

    def test_successful_operation_ids_are_deduplicated(self):
        queue_processor._write_queue([
            {"id": "same-id", "operation": "update", "path": "/Finance/a.md", "content": "x"},
            {"id": "same-id", "operation": "update", "path": "/Finance/a.md", "content": "x"},
        ])
        calls = []
        with patch.object(queue_processor, "_run_write_operation",
                          side_effect=lambda op: (calls.append(op["id"]) or (True, "ok"))):
            queue_processor.main()

        self.assertEqual(calls, ["same-id"])
        self.assertEqual(queue_processor._read_queue(), [])
        results = json.loads(queue_processor.RESULT_JSON.read_text())
        self.assertEqual([result["id"] for result in results], ["same-id"])

    def test_successful_id_from_prior_run_is_not_replayed(self):
        queue_processor._write_queue([
            {"id": "already-done", "operation": "append",
             "path": "/Finance/a.md", "content": "duplicate"}
        ])
        queue_processor.RESULT_JSON.write_text(json.dumps([{
            "id": "already-done", "success": True, "processed_at": "2026-01-01T00:00:00Z"
        }]))
        with patch.object(queue_processor, "_run_write_operation") as runner:
            queue_processor.main()
        runner.assert_not_called()
        self.assertEqual(queue_processor._read_queue(), [])

    def test_failed_writes_remain_for_retry(self):
        entries = [
            {"id": operation, "operation": operation, "path": f"/Finance/{operation}.md",
             "content": "retry"}
            for operation in ("create", "update", "append")
        ]
        queue_processor._write_queue(entries)
        with patch.object(queue_processor, "_run_write_operation",
                          return_value=(False, "temporary failure")):
            queue_processor.main()

        self.assertEqual({entry["id"] for entry in queue_processor._read_queue()},
                         {"create", "update", "append"})

    def test_conflicts_are_terminal_rebase_required_results(self):
        entries = [
            {"id": "etag-conflict", "operation": "update",
             "path": "/Finance/file.md", "content": "x"},
            {"id": "source-conflict", "operation": "update",
             "path": "/Finance/file2.md", "content": "x"},
            {"id": "http-412", "operation": "append",
             "path": "/Finance/file3.md", "content": "x"},
        ]
        queue_processor._write_queue(entries)
        outputs = [
            (False, "ERROR: Update conflict: base eTag does not match"),
            (False, "ERROR: Update source hash conflict; no write sent"),
            (False, "ERROR: Append write failed (412): precondition failed"),
        ]
        with patch.object(queue_processor, "_run_write_operation",
                          side_effect=outputs):
            queue_processor.main()

        self.assertEqual(queue_processor._read_queue(), [])
        results = json.loads(queue_processor.RESULT_JSON.read_text())
        self.assertEqual({result["id"] for result in results},
                         {"etag-conflict", "source-conflict", "http-412"})
        for result in results:
            self.assertTrue(result["rebase_required"])
            self.assertFalse(result["retryable"])
            self.assertEqual(result["error_code"], "rebase_required")
            self.assertIn("conflict", result)

    def test_authoritative_ledger_missing_base_etag_is_rejected(self):
        entries = [
            {"id": "expenses-ledger-no-base", "operation": "update",
             "path": "/Expenses/Expense ledger.md", "content": "blocked"},
            {"id": "finance-ledger-no-base", "operation": "update",
             "path": "/Finance/Finance ledger.md", "content": "blocked"},
        ]
        queue_processor._write_queue(entries)
        with patch.object(queue_processor, "_run_write_operation") as runner:
            queue_processor.main()
        runner.assert_not_called()
        results = json.loads(queue_processor.RESULT_JSON.read_text())
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertFalse(result["success"])
            self.assertIn("base_etag", result["output"])
            self.assertIn("expected_source_sha256", result["output"])
        self.assertEqual(queue_processor._read_queue(), [])

    def test_generic_create_is_rejected_for_both_canonical_ledgers(self):
        entries = [
            {
                "id": "create-existing-ledger",
                "operation": "create",
                "path": "/Expenses/Expense ledger.md",
                "content": "blocked",
                "allow_overwrite": True,
            },
            {
                "id": "create-missing-ledger",
                "operation": "create",
                "path": "/Finance/Finance ledger.md",
                "content": "blocked",
            },
        ]
        queue_processor._write_queue(entries)
        with patch.object(queue_processor, "_run_write_operation") as runner:
            queue_processor.main()
        runner.assert_not_called()
        self.assertEqual(queue_processor._read_queue(), [])
        results = json.loads(queue_processor.RESULT_JSON.read_text())
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertFalse(result["success"])
            self.assertIn("gated bootstrap", result["output"])

    def test_processor_passes_supplied_update_protocol_fields(self):
        entry = {
            "id": "ledger-with-base", "operation": "update",
            "path": "/Finance/Finance ledger.md", "content": "new",
            "base_etag": '"remote-v1"',
            "expected_source_sha256": "a" * 64,
            "content_sha256": "b" * 64,
        }
        queue_processor._write_queue([entry])
        with patch.object(queue_processor, "_run_write_operation",
                          return_value=(True, 'SP_WRITE_PROOF: {"readback_sha256": "'
                                        + "b" * 64 + '", "resulting_etag": "\\"remote-v2\\""}')) as runner:
            queue_processor.main()
        runner.assert_called_once_with(entry)
        result = json.loads(queue_processor.RESULT_JSON.read_text())[0]
        self.assertEqual(result["resulting_etag"], '"remote-v2"')
        self.assertEqual(result["readback_sha256"], "b" * 64)

    def test_authoritative_missing_write_proof_stays_retryable(self):
        entry = {
            "id": "missing-proof", "operation": "update",
            "path": "/Finance/Finance ledger.md", "content": "new",
            "base_etag": '"remote-v1"',
            "expected_source_sha256": "a" * 64,
            "content_sha256": "b" * 64,
        }
        queue_processor._write_queue([entry])
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="success without proof", stderr=""
        )
        with patch.object(queue_processor.subprocess, "run", return_value=completed):
            queue_processor.main()
        self.assertEqual(queue_processor._read_queue(), [entry])
        result = json.loads(queue_processor.RESULT_JSON.read_text())[0]
        self.assertFalse(result["success"])
        self.assertTrue(result["retryable"])

    def test_authoritative_malformed_write_proof_stays_retryable(self):
        entry = {
            "id": "malformed-proof", "operation": "append",
            "path": "/Finance/Finance ledger.md", "content": "new",
            "base_etag": '"remote-v1"',
            "expected_source_sha256": "a" * 64,
            "content_sha256": "b" * 64,
        }
        queue_processor._write_queue([entry])
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='SP_WRITE_PROOF: {"resulting_etag": "etag", '
                   '"readback_sha256": "NOT-A-SHA"}',
            stderr="",
        )
        with patch.object(queue_processor.subprocess, "run", return_value=completed):
            queue_processor.main()
        self.assertEqual(queue_processor._read_queue(), [entry])
        result = json.loads(queue_processor.RESULT_JSON.read_text())[0]
        self.assertFalse(result["success"])
        self.assertTrue(result["retryable"])

    def test_protected_path_rejection_is_not_retried(self):
        entry = {"id": "protected", "operation": "update",
                 "path": "/skills/canonical.md", "content": "blocked"}
        queue_processor._write_queue([entry])
        queue_processor.main()
        self.assertEqual(queue_processor._read_queue(), [])

    def test_producer_entry_added_during_processing_is_preserved(self):
        first = {"id": "first", "operation": "update", "path": "/Finance/a.md", "content": "x"}
        second = {"id": "second", "operation": "update", "path": "/Finance/b.md", "content": "x"}
        queue_processor._write_queue([first])

        def process(_):
            # Simulate the documented plain-file producer, which does not
            # require exec/TOTP and therefore does not take the processor lock.
            queue_processor._write_queue([first, second])
            return True, "ok"

        with patch.object(queue_processor, "_run_write_operation", side_effect=process):
            queue_processor.main()

        self.assertEqual(queue_processor._read_queue(), [second])


class SharePointWriteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.content_file = Path(self.tempdir.name) / "content.md"
        self.content_file.write_bytes(b"new content")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_update_uses_etag_and_verifies_readback(self):
        calls = []
        responses = [
            Response(payload={"eTag": '"etag-v1"'}),
            Response(payload={"eTag": '"etag-v2"', "size": 11}),
            Response(content=b"new content"),
        ]

        def request(method, *args, **kwargs):
            calls.append((method, kwargs))
            return responses.pop(0)

        with patch.object(sharepoint.requests, "get",
                          side_effect=lambda *a, **kw: request("get", *a, **kw)), \
             patch.object(sharepoint.requests, "put",
                          side_effect=lambda *a, **kw: request("put", *a, **kw)):
            sharepoint.cmd_update("token", "/Finance/file.md", "site", "drive",
                                  str(self.content_file))

        put_call = next(kwargs for method, kwargs in calls if method == "put")
        self.assertEqual(put_call["headers"]["If-Match"], '"etag-v1"')
        self.assertEqual([method for method, _ in calls], ["get", "put", "get"])

    def test_receipt_queue_adapter_consumes_real_upload_cli_json_proof(self):
        receipt = Path(self.tempdir.name) / "receipt.pdf"
        receipt.write_bytes(b"receipt bytes")
        sp_path = "/Expenses/Receipts/" + "a" * 64 + "-receipt.pdf"
        old_script = queue_processor.SP_SCRIPT
        queue_processor.SP_SCRIPT = Path(self.tempdir.name) / "sharepoint.py"
        queue_processor.SP_SCRIPT.write_text("# fixture")
        responses = [
            Response(status_code=404),
            Response(content=receipt.read_bytes()),
        ]
        uploaded = Response(payload={
            "eTag": '"receipt-v1"',
            "size": receipt.stat().st_size,
            "webUrl": "https://example.invalid/receipt.pdf",
        })
        try:
            with patch.object(sharepoint.requests, "get", side_effect=responses), \
                 patch.object(
                     sharepoint.requests,
                     "put",
                     return_value=uploaded,
                 ):
                output = io.StringIO()
                with redirect_stdout(output):
                    sharepoint.cmd_upload(
                        "token",
                        sp_path,
                        "site",
                        "drive",
                        str(receipt),
                        "application/pdf",
                    )
            cli_proof = json.loads(output.getvalue())
            self.assertEqual("uploaded", cli_proof["status"])
            self.assertEqual(sp_path, cli_proof["path"])
            self.assertEqual('"receipt-v1"', cli_proof["etag"])
            self.assertEqual(
                hashlib.sha256(receipt.read_bytes()).hexdigest(),
                cli_proof["readback_sha256"],
            )

            entry = {
                "id": "receipt-proof",
                "operation": "upload_binary",
                "path": sp_path,
                "source_path": str(receipt),
                "content_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                "mime_type": "application/pdf",
            }
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=output.getvalue(),
                stderr="",
            )
            with patch.object(
                queue_processor.subprocess,
                "run",
                return_value=completed,
            ) as runner:
                success, adapter_output = queue_processor._run_binary_upload_operation(entry)
            self.assertTrue(success)
            self.assertEqual(cli_proof, json.loads(adapter_output))
            self.assertEqual(
                [
                    "python3",
                    str(queue_processor.SP_SCRIPT),
                    "upload",
                    sp_path,
                    "--content-file",
                    str(receipt),
                    "--mime-type",
                    "application/pdf",
                ],
                runner.call_args.args[0],
            )
        finally:
            queue_processor.SP_SCRIPT = old_script

    def test_update_conflict_never_writes_and_ledger_requires_base_etag(self):
        responses = [Response(payload={"eTag": '"remote-v2"'})]
        with patch.object(sharepoint.requests, "get", side_effect=responses), \
             patch.object(sharepoint.requests, "put") as put:
            with self.assertRaises(SystemExit) as conflict:
                sharepoint.cmd_update(
                    "token", "/Finance/file.md", "site", "drive",
                    str(self.content_file), '"remote-v1"',
                )
        self.assertEqual(conflict.exception.code, 2)
        put.assert_not_called()

        with patch.object(sharepoint.requests, "get") as get:
            with self.assertRaises(SystemExit) as missing_hash:
                sharepoint.cmd_update(
                    "token", "/Expenses/Expense ledger.md", "site", "drive",
                    str(self.content_file), '"remote-v1"',
                )
        self.assertEqual(missing_hash.exception.code, 3)
        get.assert_not_called()

        with patch.object(sharepoint.requests, "get") as get:
            with self.assertRaises(SystemExit) as missing:
                sharepoint.cmd_update(
                    "token", "/Expenses/Expense ledger.md", "site", "drive",
                    str(self.content_file),
                )
        self.assertEqual(missing.exception.code, 3)
        get.assert_not_called()

    def test_cli_create_rejects_existing_or_missing_canonical_ledger(self):
        for path, allow_overwrite in (
            ("/Expenses/Expense ledger.md", True),
            ("/Finance/Finance ledger.md", False),
        ):
            with patch.object(sharepoint.requests, "get") as get:
                with self.assertRaises(SystemExit) as rejected:
                    sharepoint.cmd_create(
                        "token", path, "site", "drive",
                        str(self.content_file), allow_overwrite,
                    )
            self.assertEqual(rejected.exception.code, 3)
            get.assert_not_called()

    def test_expected_source_hash_is_checked_before_update(self):
        calls = []
        responses = [
            Response(payload={"eTag": '"etag-v1"'}),
            Response(content=b"remote source"),
        ]

        def request(method, *args, **kwargs):
            calls.append((method, kwargs))
            return responses.pop(0)

        with patch.object(sharepoint.requests, "get",
                          side_effect=lambda *a, **kw: request("get", *a, **kw)), \
             patch.object(sharepoint.requests, "put") as put:
            with self.assertRaises(SystemExit) as conflict:
                sharepoint.cmd_update(
                    "token", "/Finance/file.md", "site", "drive",
                    str(self.content_file), '"etag-v1"', "0" * 64,
                )
        self.assertEqual(conflict.exception.code, 2)
        put.assert_not_called()
        self.assertEqual([method for method, _ in calls], ["get", "get"])

    def test_evicted_successful_result_replay_fails_on_stale_base_etag(self):
        # Once a result falls out of the bounded receipt log, the remote
        # version check remains the durable idempotency barrier.
        queue_processor.RESULT_JSON = Path(self.tempdir.name) / "evicted-results.json"
        queue_processor.RESULT_JSON.write_text(json.dumps([
            {"id": f"old-{index}", "success": True,
             "processed_at": f"2026-01-01T00:00:{index:02d}Z"}
            for index in range(1000)
        ]))
        self.assertNotIn("evicted-ledger-op", queue_processor._successful_operation_ids())

        with patch.object(sharepoint.requests, "get",
                          return_value=Response(payload={"eTag": '"remote-v2"'})), \
             patch.object(sharepoint.requests, "put") as put:
            with self.assertRaises(SystemExit) as conflict:
                sharepoint.cmd_update(
                    "token", "/Expenses/Expense ledger.md", "site", "drive",
                    str(self.content_file), '"remote-v1"', "0" * 64,
                )
        self.assertEqual(conflict.exception.code, 2)
        put.assert_not_called()

    def test_append_uses_etag_and_verifies_combined_readback(self):
        calls = []
        combined = b"existing\n\nnew content"
        responses = [
            Response(payload={"eTag": '"etag-v1"'}),
            Response(content=b"existing"),
            Response(payload={"eTag": '"etag-v2"', "size": len(combined)}),
            Response(content=combined),
        ]

        def request(method, *args, **kwargs):
            calls.append((method, kwargs))
            return responses.pop(0)

        with patch.object(sharepoint.requests, "get",
                          side_effect=lambda *a, **kw: request("get", *a, **kw)), \
             patch.object(sharepoint.requests, "put",
                          side_effect=lambda *a, **kw: request("put", *a, **kw)):
            sharepoint.cmd_append("token", "/Finance/file.md", "site", "drive",
                                  str(self.content_file))

        put_call = next(kwargs for method, kwargs in calls if method == "put")
        self.assertEqual(put_call["headers"]["If-Match"], '"etag-v1"')
        self.assertEqual(put_call["data"], combined)
        self.assertEqual([method for method, _ in calls], ["get", "get", "put", "get"])

    def test_readback_mismatch_is_failure(self):
        responses = [
            Response(payload={"eTag": '"etag-v1"'}),
            Response(payload={"eTag": '"etag-v2"'}),
            Response(content=b"not the write"),
        ]
        with patch.object(sharepoint.requests, "get", side_effect=responses), \
             patch.object(sharepoint.requests, "put",
                          return_value=Response(payload={"eTag": '"etag-v2"', "size": 11})):
            with self.assertRaises(SystemExit) as raised:
                sharepoint.cmd_update("token", "/Finance/file.md", "site", "drive",
                                      str(self.content_file))
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
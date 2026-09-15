from __future__ import annotations

import base64
import contextlib
import hashlib
import http.server
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from seer_finance.ledger.sharepoint_contract import (
    FINANCE_LEDGER_PATH,
    SharePointDocumentStore,
    SharePointWritePending,
)
from seer_finance.ledger.workbook_codec import WorkbookCodec


ROOT = Path(__file__).parents[3]
MICROSOFT = ROOT / "attached_assets" / "integrations" / "microsoft"


def _load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load integration module {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


class _GraphState:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.etag = '"e0"'
        self.version = '"c0"'
        self.puts = 0


class _GraphHandler(http.server.BaseHTTPRequestHandler):
    state: _GraphState

    def log_message(self, *_args: object) -> None:
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        state = self.state
        if path.endswith("/root/children"):
            self._json({
                "value": [{
                    "name": "Finance",
                    "folder": {"childCount": 1},
                    "id": "folder",
                }],
            })
            return
        if path.endswith("/root:/Finance:/children"):
            self._json({
                "value": [{
                    "name": "Finance ledger.xlsx",
                    "file": {},
                    "id": "file",
                    "size": len(state.content),
                    "lastModifiedDateTime": "2026-09-15T00:00:00Z",
                    "eTag": state.etag,
                    "cTag": state.version,
                }],
            })
            return
        if path.endswith(":/content"):
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            self.send_header("ETag", state.etag)
            self.send_header("Content-Length", str(len(state.content)))
            self.end_headers()
            self.wfile.write(state.content)
            return
        if path.endswith("/root:/Finance/Finance ledger.xlsx"):
            self._json({
                "id": "file",
                "name": "Finance ledger.xlsx",
                "eTag": state.etag,
                "cTag": state.version,
                "size": len(state.content),
            })
            return
        self._json({}, status=404)

    def do_PUT(self) -> None:
        path = unquote(urlparse(self.path).path)
        state = self.state
        if not path.endswith(":/content"):
            self._json({}, status=404)
            return
        if self.headers.get("If-Match") != state.etag:
            self._json({"error": "etag conflict"}, status=412)
            return
        length = int(self.headers.get("Content-Length", "0"))
        state.content = self.rfile.read(length)
        state.puts += 1
        state.etag = f'"e{state.puts}"'
        state.version = f'"c{state.puts}"'
        self._json({
            "id": "file",
            "eTag": state.etag,
            "cTag": state.version,
            "size": len(state.content),
        })


class SharePointWorkbookEndToEndTests(unittest.TestCase):
    def test_store_queue_mock_graph_poller_store_exact_workbook_proof(self) -> None:
        initial = WorkbookCodec.encode_finance({
            "schema_version": 1,
            "transactions": [],
        })
        desired = WorkbookCodec.encode_finance({
            "schema_version": 1,
            "transactions": [{
                "txn_id": "e2e-1",
                "date": "2026-09-15",
                "direction": "expense",
                "amount_pence": 1200,
                "description": "Visible workbook edit",
                "counterparty": "Acme",
                "category": "software",
                "pre_trading": False,
                "tax_treatment": None,
                "source_ref": "fixture:e2e",
            }],
        })

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            target = cache / "Finance" / "Finance ledger.xlsx"
            target.parent.mkdir(parents=True)
            target.write_bytes(initial)
            synced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            (cache / ".manifest.json").write_text(
                json.dumps({
                    "cached": {
                        "Finance/Finance ledger.xlsx": {
                            "sp_path": FINANCE_LEDGER_PATH,
                            "etag": '"e0"',
                            "version": '"c0"',
                            "synced_at": synced_at,
                            "content_sha256": hashlib.sha256(initial).hexdigest(),
                            "semantic_sha256": WorkbookCodec.semantic_hash(initial),
                        }
                    }
                }),
                encoding="utf-8",
            )

            queue = root / "queue.json"
            results = root / "results.json"
            store = SharePointDocumentStore(
                queue_path=queue,
                results_path=results,
                cache_root=cache,
            )
            with self.assertRaises(SharePointWritePending):
                store.write_workbook(
                    path=FINANCE_LEDGER_PATH,
                    content_base64=base64.b64encode(desired).decode("ascii"),
                    content_sha256=hashlib.sha256(desired).hexdigest(),
                    base_etag='"e0"',
                    expected_source_sha256=hashlib.sha256(initial).hexdigest(),
                    semantic_workbook_sha256=WorkbookCodec.semantic_hash(desired),
                )

            _load_module("sharepoint_workbook", MICROSOFT / "sharepoint_workbook.py")
            sharepoint = _load_module("e2e_sharepoint", MICROSOFT / "sharepoint.py")
            queue_processor = _load_module(
                "e2e_sharepoint_queue_processor",
                MICROSOFT / "sharepoint_queue_processor.py",
            )
            poller = _load_module(
                "e2e_sharepoint_cache_poller",
                MICROSOFT / "sharepoint_cache_poller.py",
            )

            state = _GraphState(initial)
            _GraphHandler.state = state
            server = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), _GraphHandler
            )
            server_thread = threading.Thread(
                target=server.serve_forever, daemon=True
            )
            server_thread.start()
            old_host = os.environ.get("SHAREPOINT_HOST")
            old_subprocess_run = None
            try:
                graph_base = f"http://127.0.0.1:{server.server_port}/v1.0"
                sharepoint.GRAPH_BASE = graph_base
                poller.GRAPH_BASE = graph_base
                queue_processor.QUEUE_FILE = queue
                queue_processor.RESULT_JSON = results
                queue_processor.RESULT_MD = root / "result.md"
                queue_processor.LOCK_FILE = root / "queue.lock"
                queue_processor.LOG_FILE = root / "queue.log"
                queue_processor.WORKSPACE = root / "workspace"
                queue_processor.SP_SCRIPT = root / "sharepoint.py"
                queue_processor.SP_SCRIPT.write_text("# local fixture\n")
                old_subprocess_run = queue_processor.subprocess.run

                def run_sharepoint(
                    command: list[str],
                    *,
                    capture_output: bool = True,
                    text: bool = True,
                    timeout: int = 90,
                ):
                    del capture_output, text, timeout
                    values = list(command)

                    def argument(flag: str) -> str:
                        return values[values.index(flag) + 1]

                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        try:
                            sharepoint.cmd_update_workbook(
                                "fixture-token",
                                "/Finance/Finance ledger.xlsx",
                                "site",
                                "drive",
                                argument("--content-file"),
                                argument("--content-sha256"),
                                argument("--base-etag"),
                                argument("--expected-source-sha256"),
                                argument("--semantic-sha256"),
                            )
                        except SystemExit as error:
                            return type(
                                "Completed",
                                (),
                                {
                                    "returncode": error.code,
                                    "stdout": stdout.getvalue(),
                                    "stderr": stderr.getvalue(),
                                },
                            )()
                    return type(
                        "Completed",
                        (),
                        {
                            "returncode": 0,
                            "stdout": stdout.getvalue(),
                            "stderr": stderr.getvalue(),
                        },
                    )()

                queue_processor.subprocess.run = run_sharepoint
                with contextlib.redirect_stdout(io.StringIO()):
                    queue_processor.main()
                self.assertEqual(desired, state.content)
                self.assertEqual(1, state.puts)
                proof = json.loads(results.read_text(encoding="utf-8"))[0]
                self.assertTrue(proof["success"])
                self.assertEqual(
                    hashlib.sha256(desired).hexdigest(),
                    proof["readback_sha256"],
                )
                self.assertEqual(
                    WorkbookCodec.semantic_hash(desired),
                    proof["readback_semantic_workbook_sha256"],
                )

                poller.WORKSPACE = root
                poller.CACHE_DIR = cache
                poller.MANIFEST = cache / ".manifest.json"
                poller.INDEX_MD = root / "SHAREPOINT_INDEX.md"
                poller._get_access_token = lambda: "fixture-token"
                poller._resolve_site_and_drive = lambda _token: ("site", "drive")
                os.environ["SHAREPOINT_HOST"] = "fixture"
                with contextlib.redirect_stdout(io.StringIO()):
                    poller.main()

                self.assertEqual(desired, target.read_bytes())
                snapshot = store.read_workbook_snapshot(FINANCE_LEDGER_PATH)
                self.assertEqual(desired, snapshot["content_bytes"])
                self.assertEqual('"e1"', snapshot["etag"])
                self.assertEqual('"c1"', snapshot["version"])
                self.assertEqual(
                    WorkbookCodec.semantic_hash(desired),
                    snapshot["semantic_sha256"],
                )

                operation = json.loads(queue.read_text(encoding="utf-8")) if queue.exists() else []
                self.assertEqual([], operation)
                journal = store._read_journal()
                self.assertEqual("pending", journal[0]["state"])
                # The successful processor proof is the durable handoff; the
                # next store call reconciles that proof against poller cache.
                operation_id = store.write_workbook(
                    path=FINANCE_LEDGER_PATH,
                    content_base64=base64.b64encode(desired).decode("ascii"),
                    content_sha256=hashlib.sha256(desired).hexdigest(),
                    base_etag='"e1"',
                    expected_source_sha256=hashlib.sha256(desired).hexdigest(),
                    semantic_workbook_sha256=WorkbookCodec.semantic_hash(desired),
                )
                self.assertEqual(journal[0]["id"], operation_id)
                self.assertEqual("verified", store._read_journal()[0]["state"])
            finally:
                if old_host is None:
                    os.environ.pop("SHAREPOINT_HOST", None)
                else:
                    os.environ["SHAREPOINT_HOST"] = old_host
                if old_subprocess_run is not None:
                    queue_processor.subprocess.run = old_subprocess_run
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
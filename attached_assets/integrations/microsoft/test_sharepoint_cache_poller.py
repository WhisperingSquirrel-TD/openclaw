#!/usr/bin/env python3
import importlib.util
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).parent


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


poller = load_module("sharepoint_cache_poller", "sharepoint_cache_poller.py")
CONTRACT_PATH = (
    Path(__file__).parents[3]
    / "pi-services"
    / "seer-finance"
    / "seer_finance"
    / "ledger"
    / "sharepoint_contract.py"
)
contract = load_module("seer_finance_sharepoint_contract", str(CONTRACT_PATH))


class CachePollerManifestTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.old = {
            "CACHE_DIR": poller.CACHE_DIR,
            "WORKSPACE": poller.WORKSPACE,
            "MANIFEST": poller.MANIFEST,
        }
        poller.WORKSPACE = root
        poller.CACHE_DIR = root / "sharepoint-cache"
        poller.MANIFEST = poller.CACHE_DIR / ".manifest.json"

    def tearDown(self):
        for name, value in self.old.items():
            setattr(poller, name, value)
        self.tempdir.cleanup()

    def test_graph_metadata_is_carried_into_manifest(self):
        files = []
        item = {
            "name": "Expense ledger.md",
            "size": 20,
            "lastModifiedDateTime": "2026-09-15T12:00:00Z",
            "id": "drive-item-1",
            "eTag": '"remote-etag"',
            "cTag": '"content-version"',
        }
        with patch.object(poller, "_list_children", return_value=[item]):
            poller._collect_all_files("token", "site", "drive", "Expenses", files)
        self.assertEqual(files[0]["etag"], '"remote-etag"')
        self.assertEqual(files[0]["version"], '"content-version"')

    def test_item_id_is_not_used_as_content_version(self):
        files = []
        item = {
            "name": "Unversioned.md",
            "size": 10,
            "id": "stable-drive-item-id",
            "eTag": '"remote-etag"',
        }
        with patch.object(poller, "_list_children", return_value=[item]):
            poller._collect_all_files("token", "site", "drive", "", files)
        self.assertEqual(files[0]["version"], "")

    def test_download_is_accepted_only_when_metadata_is_stable(self):
        identities = [
            {"etag": '"v1"', "version": '"content-1"'},
            {"etag": '"v2"', "version": '"content-2"'},
            {"etag": '"v2"', "version": '"content-2"'},
            {"etag": '"v2"', "version": '"content-2"'},
        ]
        with patch.object(
            poller, "_fetch_file_metadata", side_effect=identities
        ) as metadata, patch.object(
            poller, "_fetch_file_content", return_value="body"
        ) as content:
            body, identity = poller._fetch_consistent_file_content(
                "token", "site", "drive", "/Finance/file.md"
            )
        self.assertEqual(body, "body")
        self.assertEqual(identity, identities[-1])
        self.assertEqual(metadata.call_count, 4)
        self.assertEqual(content.call_count, 2)

    def test_cache_hash_preserves_leading_blank_lines_and_utf8_bytes(self):
        body = "\n\nCafé — naïve\n"
        local_path = poller._local_path_for("/Finance/leading.md")
        poller._write_cached_file(
            local_path, "/Finance/leading.md", body, "2026-09-15T12:00:00Z"
        )
        self.assertEqual(
            poller._cached_body(local_path.read_text(encoding="utf-8")), body
        )
        self.assertEqual(
            poller._cached_file_sha256(local_path),
            hashlib.sha256(body.encode("utf-8")).hexdigest(),
        )

    def test_content_download_uses_conditional_etag_and_strict_utf8(self):
        class Response:
            ok = True
            status_code = 200
            text = ""
            content = "Café\n".encode("utf-8")
            headers = {"ETag": '"remote-v1"'}

        with patch.object(poller.requests, "get", return_value=Response()) as get:
            content = poller._fetch_file_content(
                "token", "site", "drive", "/Finance/file.md", if_match='"remote-v1"'
            )
        self.assertEqual(content, "Café\n")
        self.assertEqual(get.call_args.kwargs["headers"]["If-Match"], '"remote-v1"')

    def test_content_download_rejects_cdn_etag_mismatch(self):
        class Response:
            ok = True
            status_code = 200
            text = ""
            content = b"stale"
            headers = {"ETag": '"remote-old"'}

        with patch.object(poller.requests, "get", return_value=Response()):
            with self.assertRaises(RuntimeError):
                poller._fetch_file_content(
                    "token", "site", "drive", "/Finance/file.md",
                    if_match='"remote-new"',
                )

    def test_content_download_rejects_invalid_utf8(self):
        class Response:
            ok = True
            status_code = 200
            text = ""
            content = b"\xff"
            headers = {"ETag": '"remote-v1"'}

        with patch.object(poller.requests, "get", return_value=Response()):
            with self.assertRaises(RuntimeError):
                poller._fetch_file_content(
                    "token", "site", "drive", "/Finance/file.md",
                    if_match='"remote-v1"',
                )

    def test_manifest_output_satisfies_seer_finance_read_snapshot(self):
        synced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        body = '{"schema_version": 1, "transactions": []}\n'
        local_path = poller._local_path_for("/Finance/Finance ledger.md")
        poller._write_cached_file(
            local_path, "/Finance/Finance ledger.md", body, synced_at
        )
        entry = {
            "sp_path": "/Finance/Finance ledger.md",
            "size": len(body.encode("utf-8")),
            "sp_modified": synced_at,
            "etag": '"remote-etag"',
            "version": '"content-version"',
            "synced_at": synced_at,
            "local_path": str(local_path.relative_to(poller.WORKSPACE)),
            "content_sha256": poller._cached_file_sha256(local_path),
        }
        poller._write_manifest(
            {"Finance/Finance ledger.md": entry}, {}, [], synced_at
        )

        store = contract.SharePointDocumentStore(cache_root=poller.CACHE_DIR)
        snapshot = store.read_snapshot("/Finance/Finance ledger.md")
        self.assertEqual(snapshot["content"], body)
        self.assertEqual(snapshot["etag"], '"remote-etag"')
        self.assertEqual(snapshot["version"], '"content-version"')
        self.assertEqual(snapshot["content_sha256"], entry["content_sha256"])
        manifest = json.loads(poller.MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["cached"]["Finance/Finance ledger.md"]["content_sha256"],
            entry["content_sha256"],
        )

    def test_leading_blank_body_is_consumed_or_fails_closed(self):
        synced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        body = "\n\nCafé — preserved\n"
        local_path = poller._local_path_for("/Finance/Finance ledger.md")
        poller._write_cached_file(
            local_path, "/Finance/Finance ledger.md", body, synced_at
        )
        entry = {
            "sp_path": "/Finance/Finance ledger.md",
            "size": len(body.encode("utf-8")),
            "sp_modified": synced_at,
            "etag": '"remote-etag"',
            "version": '"content-version"',
            "synced_at": synced_at,
            "local_path": str(local_path.relative_to(poller.WORKSPACE)),
            "content_sha256": poller._cached_file_sha256(local_path),
        }
        poller._write_manifest(
            {"Finance/Finance ledger.md": entry}, {}, [], synced_at
        )
        store = contract.SharePointDocumentStore(cache_root=poller.CACHE_DIR)
        try:
            snapshot = store.read_snapshot("/Finance/Finance ledger.md")
        except contract.SharePointCacheUnavailable:
            # The currently deployed finance contract strips leading newlines
            # after its header removal; it must fail closed rather than accept
            # a mismatched declared hash. A future aligned contract may consume
            # the exact body and take the branch below.
            return
        self.assertEqual(snapshot["content"], body)
        self.assertEqual(snapshot["content_sha256"], entry["content_sha256"])


if __name__ == "__main__":
    unittest.main()
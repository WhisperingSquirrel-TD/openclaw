#!/usr/bin/env python3
import importlib.util
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("authorize.py")


class _FakeCache:
    def __init__(self):
        self.serialized = ""

    def deserialize(self, value):
        self.serialized = value

    def serialize(self):
        return self.serialized or "fixture-cache"


class _FakePublicClientApplication:
    initiate_device_flow_called = False
    silent_scopes = None

    def __init__(self, client_id, *, authority, token_cache):
        self.client_id = client_id
        self.authority = authority
        self.token_cache = token_cache

    def get_accounts(self):
        return ["fixture-account"]

    def acquire_token_silent(self, scopes, *, account):
        type(self).silent_scopes = scopes
        return {"access_token": "fixture-access-token"}

    def initiate_device_flow(self, *, scopes):
        type(self).initiate_device_flow_called = True
        raise AssertionError("OAuth device flow must not run in cache-only test")


fake_msal = types.SimpleNamespace(
    SerializableTokenCache=_FakeCache,
    PublicClientApplication=_FakePublicClientApplication,
)
with patch.dict(sys.modules, {"msal": fake_msal}):
    spec = importlib.util.spec_from_file_location("external_email_authorize", MODULE_PATH)
    authorize = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(authorize)


class PrivateCacheTests(unittest.TestCase):
    def test_atomic_cache_is_regular_owner_only_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "token.json"

            authorize._atomic_write_private_cache(path, "fixture-cache")

            metadata = path.stat()
            self.assertTrue(stat.S_ISREG(metadata.st_mode))
            self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)
            self.assertEqual(authorize._read_private_cache(path), "fixture-cache")
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_existing_cache_is_repaired_to_owner_only_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "token.json"
            path.write_text("fixture-cache", encoding="utf-8")
            path.chmod(0o644)

            self.assertEqual(authorize._read_private_cache(path), "fixture-cache")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_symlink_cache_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = directory / "target.json"
            link = directory / "token.json"
            target.write_text("unchanged", encoding="utf-8")
            os.symlink(target, link)

            with self.assertRaises(RuntimeError):
                authorize._atomic_write_private_cache(link, "replacement")

            self.assertTrue(link.is_symlink())
            self.assertEqual(target.read_text(encoding="utf-8"), "unchanged")

    def test_symlink_cache_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target_directory = directory / "target"
            target_directory.mkdir()
            link_directory = directory / "credentials"
            os.symlink(target_directory, link_directory)

            with self.assertRaises(RuntimeError):
                authorize._atomic_write_private_cache(
                    link_directory / "token.json",
                    "replacement",
                )

            self.assertFalse((target_directory / "token.json").exists())

    def test_cached_authorization_never_starts_oauth(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "token.json"
            authorize._atomic_write_private_cache(path, "fixture-cache")
            _FakePublicClientApplication.initiate_device_flow_called = False
            _FakePublicClientApplication.silent_scopes = None

            with patch.object(authorize, "TOKEN_FILE", path):
                authorize.main()

            self.assertFalse(_FakePublicClientApplication.initiate_device_flow_called)
            self.assertEqual(_FakePublicClientApplication.silent_scopes, ["Mail.Read"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()

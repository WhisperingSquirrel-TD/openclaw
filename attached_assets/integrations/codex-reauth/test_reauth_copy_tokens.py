import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("reauth-copy-tokens.py")


def fake_jwt(claims):
    def segment(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    return f"{segment({'alg': 'none', 'typ': 'JWT'})}.{segment(claims)}.signature"


class CodexProfileShapeTests(unittest.TestCase):
    def run_copy(self, home, codex_tokens):
        codex_dir = home / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "auth.json").write_text(json.dumps({"tokens": codex_tokens}))
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            env={**os.environ, "HOME": str(home)},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_updates_list_shape_and_top_level_credential(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            main_auth = home / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
            other_auth = home / ".openclaw" / "agents" / "worker" / "agent" / "auth-profiles.json"
            main_auth.parent.mkdir(parents=True)
            other_auth.parent.mkdir(parents=True)
            main_auth.write_text(
                json.dumps(
                    {
                        "profiles": ["existing"],
                        "openai-codex:default": {"legacy": "preserve"},
                    }
                )
            )
            other_auth.write_text(json.dumps({"profiles": {}}))
            access = fake_jwt(
                {
                    "exp": 4_000_000_000,
                    "https://api.openai.com/auth": {"chatgpt_account_id": "claim-account"},
                }
            )

            result = self.run_copy(
                home,
                {
                    "access_token": access,
                    "refresh_token": "refresh-fixture",
                },
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            updated = json.loads(main_auth.read_text())
            self.assertEqual(updated["profiles"], ["existing", "openai-codex:default"])
            self.assertEqual(
                updated["openai-codex:default"],
                {
                    "legacy": "preserve",
                    "type": "oauth",
                    "provider": "openai-codex",
                    "access": access,
                    "refresh": "refresh-fixture",
                    "expires": 4_000_000_000_000,
                    "accountId": "claim-account",
                },
            )
            worker = json.loads(other_auth.read_text())
            self.assertEqual(worker["profiles"]["openai-codex:default"]["accountId"], "claim-account")

    def test_updates_dict_shape_and_prefers_explicit_account_id(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            main_auth = home / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
            main_auth.parent.mkdir(parents=True)
            main_auth.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "openai-codex:default": {"old": "preserve"},
                            "other": {"type": "api_key"},
                        }
                    }
                )
            )
            access = fake_jwt({"exp": 4_000_000_001})

            result = self.run_copy(
                home,
                {
                    "access_token": access,
                    "refresh_token": "refresh-fixture",
                    "account_id": "explicit-account",
                },
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            updated = json.loads(main_auth.read_text())
            self.assertEqual(updated["profiles"]["other"], {"type": "api_key"})
            self.assertEqual(
                updated["profiles"]["openai-codex:default"],
                {
                    "old": "preserve",
                    "type": "oauth",
                    "provider": "openai-codex",
                    "access": access,
                    "refresh": "refresh-fixture",
                    "expires": 4_000_000_001_000,
                    "accountId": "explicit-account",
                },
            )


if __name__ == "__main__":
    unittest.main()
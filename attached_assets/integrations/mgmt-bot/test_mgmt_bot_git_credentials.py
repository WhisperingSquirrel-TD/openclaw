"""Offline regression tests for management-bot Git credential handling.

These tests deliberately use synthetic credential strings and a mocked git
subprocess.  They never contact GitHub or run a real clone/push.
"""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "mgmt-bot.py"
SPEC = importlib.util.spec_from_file_location("mgmt_bot_git_credentials", SOURCE)
mgmt_bot = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(mgmt_bot)


class GitCredentialHandlingTests(unittest.TestCase):
    """Exercise clone/push without placing fixture credentials in argv."""

    fixture_token = "fixture-token-not-a-real-secret"
    fixture_session_secret = "fixture-session-not-a-real-secret"
    clean_url = "https://github.com/example/private-repo.git"

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmpdir.name) / ".openclaw"
        self.project_dir = self.state_dir / "workspace" / "projects" / "demo"
        self.calls = []
        self.messages = []

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_command(self, operation, args):
        self.project_dir.mkdir(parents=True, exist_ok=True)
        cmd_file = self.project_dir / ".dev-cmd.json"
        cmd_file.write_text(json.dumps({
            "project": "demo",
            "operation": operation,
            "args": args,
        }))
        return cmd_file

    @staticmethod
    def _git_args(argv):
        """Return git subcommand arguments after command-scoped config flags."""
        args = list(argv[1:])
        while args[:1] == ["-c"]:
            args = args[2:]
        return args

    @staticmethod
    def _is_git_argv(argv):
        """Git must be invoked through the validated absolute binary."""
        return (
            argv
            and Path(argv[0]).name == "git"
            and Path(argv[0]).is_absolute()
        )

    def _fake_git(self, push_output=""):
        def fake_run(argv, **kwargs):
            argv = list(argv)
            self.calls.append((argv, kwargs))
            args = self._git_args(argv)

            if args[:1] == ["clone"]:
                clone_url, destination = args[-2:]
                config = Path(destination) / ".git" / "config"
                config.parent.mkdir(parents=True, exist_ok=True)
                config.write_text(
                    '[remote "origin"]\n\turl = ' + clone_url + "\n"
                )
                return SimpleNamespace(returncode=0, stdout="cloned", stderr="")

            if args[:3] == ["remote", "get-url", "origin"]:
                config = self.project_dir / ".git" / "config"
                url = config.read_text().split("url = ", 1)[1].strip()
                return SimpleNamespace(returncode=0, stdout=url + "\n", stderr="")

            if args[:3] == ["remote", "set-url", "origin"]:
                config = self.project_dir / ".git" / "config"
                config.write_text('[remote "origin"]\n\turl = ' + args[3] + "\n")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            if args[:2] == ["push", "-u"] and push_output:
                return SimpleNamespace(returncode=1, stdout="", stderr=push_output)
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")

        return fake_run

    def _execute(self, cmd_file, fake_run):
        with (
            patch.object(mgmt_bot, "STATE_DIR", self.state_dir),
            patch.object(mgmt_bot.subprocess, "run", side_effect=fake_run),
            patch.object(mgmt_bot, "send", side_effect=lambda *args: self.messages.append(args[2])),
            patch.dict(os.environ, {
                "HOME": str(Path(self.tmpdir.name) / "fixture-home"),
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "GITHUB_TOKEN": self.fixture_token,
                "SESSION_SECRET": self.fixture_session_secret,
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "credential.helper",
                "GIT_CONFIG_VALUE_0": "malicious-fixture-helper",
            }, clear=True),
        ):
            mgmt_bot._execute_dev_cmd("telegram-fixture", "1", cmd_file)

    def _assert_no_fixture_credential_in_argv(self):
        all_argv = "\n".join(" ".join(call[0]) for call in self.calls)
        self.assertNotIn(self.fixture_token, all_argv)
        self.assertNotIn(self.fixture_session_secret, all_argv)
        for argv, kwargs in self.calls:
            allowed_keys = {
                "HOME", "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
                "TMPDIR", "TMP", "TEMP", "GIT_CONFIG_NOSYSTEM",
                "GIT_CONFIG_GLOBAL", "GIT_TERMINAL_PROMPT",
                "npm_config_userconfig", "npm_config_globalconfig",
                "GIT_ALLOW_PROTOCOL", "GIT_EXEC_PATH", "GITHUB_TOKEN",
            }
            self.assertFalse(
                set(kwargs["env"]) - allowed_keys,
                "repo environment contains a non-allowlisted variable",
            )
            self.assertFalse(
                self.fixture_session_secret in kwargs["env"].values(),
                "repo subprocess must not inherit unrelated bot secrets",
            )
            self.assertFalse(
                "GIT_CONFIG_COUNT" in kwargs["env"],
                "repo subprocess must not inherit caller Git config overrides",
            )
            if not self._is_git_argv(argv):
                self.assertNotIn(
                    "GITHUB_TOKEN", kwargs["env"],
                    "npm must not inherit the GitHub token",
                )
                continue
            git_args = self._git_args(argv)
            self.assertIn("core.hooksPath=/dev/null", " ".join(argv))
            self.assertIn("core.fsmonitor=false", " ".join(argv))
            self.assertIn("core.fsmonitorHookVersion=", " ".join(argv))
            self.assertIn("credential.helper=", " ".join(argv))
            if git_args[0] in {"clone", "fetch", "push"}:
                self.assertEqual(kwargs["env"]["GITHUB_TOKEN"], self.fixture_token)
                self.assertEqual(kwargs["env"]["GIT_ALLOW_PROTOCOL"], "https")
                self.assertIn(
                    "credential.helper=" + mgmt_bot._SCOPED_GIT_CREDENTIAL_HELPER,
                    " ".join(argv),
                )
            else:
                self.assertNotIn(
                    "GITHUB_TOKEN", kwargs["env"],
                    "checkout/local Git must not receive the GitHub token",
                )
                self.assertFalse(
                    "GIT_ALLOW_PROTOCOL" in kwargs["env"],
                    "checkout/local Git must not receive the network transport override",
                )

    def test_clone_uses_scoped_helper_and_keeps_origin_credential_free(self):
        cmd_file = self._write_command("git_clone", {
            "url": self.clean_url,
            "branch": "main",
        })
        self._execute(cmd_file, self._fake_git())

        self._assert_no_fixture_credential_in_argv()
        origin = (self.project_dir / ".git" / "config").read_text()
        self.assertIn(self.clean_url, origin)
        self.assertNotIn(self.fixture_token, origin)
        self.assertEqual(
            [self._git_args(argv)[0] for argv, _ in self.calls],
            ["clone", "remote", "remote", "checkout"],
        )

    def test_clone_rejects_credential_bearing_and_encoded_noncanonical_urls(self):
        encoded_fixture = urllib.parse.quote(
            self.fixture_token, safe=""
        ).replace("-", "%2D", 1)
        adversarial_urls = [
            self.clean_url + "?access_token=" + self.fixture_token,
            self.clean_url + "?access%5Ftoken=" + encoded_fixture,
            self.clean_url + "#token=" + self.fixture_token,
            "https://" + self.fixture_token + "@github.com/example/private-repo.git",
            "https://github.com/example%2Fprivate-repo.git",
        ]

        for index, url in enumerate(adversarial_urls):
            with self.subTest(url_kind=f"case-{index}"):
                self.calls = []
                self.messages = []
                cmd_file = self._write_command("git_clone", {
                    "url": url,
                    "branch": "main",
                })
                self._execute(cmd_file, self._fake_git())

                self.assertFalse(self.calls, "rejected URL must not reach subprocess")
                output = "\n".join(self.messages)
                self.assertFalse(
                    self.fixture_token in output,
                    "rejection must not return the fixture credential",
                )
                self.assertFalse(
                    encoded_fixture in output,
                    "rejection must not return the encoded fixture credential",
                )
                self.assertIn("canonical", output)

    def test_npm_execution_uses_minimal_secret_free_environment(self):
        cmd_file = self._write_command("npm_install", {})
        self._execute(cmd_file, self._fake_git())

        self.assertEqual(len(self.calls), 1)
        argv, kwargs = self.calls[0]
        self.assertEqual(argv, ["npm", "install"])
        self.assertFalse(
            "GITHUB_TOKEN" in kwargs["env"],
            "npm environment must not contain GITHUB_TOKEN",
        )
        self.assertFalse(
            "SESSION_SECRET" in kwargs["env"],
            "npm environment must not contain SESSION_SECRET",
        )
        self.assertEqual(kwargs["env"]["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(kwargs["env"]["GIT_CONFIG_NOSYSTEM"], "1")

    def test_authenticated_git_ignores_home_planted_binary_offline(self):
        """A real local Git invocation must not execute a HOME/bin impostor."""
        home = Path(self.tmpdir.name) / "planted-home"
        planted_bin = home / ".npm-global" / "bin"
        planted_bin.mkdir(parents=True)
        marker = home / "attacker-ran.txt"
        (planted_bin / "git").write_text(
            "#!/bin/sh\n"
            f"printf 'GITHUB_TOKEN=%s\\n' \"$GITHUB_TOKEN\" > {marker!s}\n"
            "exit 97\n"
        )
        # This is a fixture file under TemporaryDirectory, not a system or
        # repository permission change.
        os.chmod(planted_bin / "git", 0o755)

        with patch.dict(os.environ, {
            "HOME": str(home),
            "PATH": str(planted_bin) + ":/usr/bin:/bin",
            "GITHUB_TOKEN": self.fixture_token,
            "SESSION_SECRET": self.fixture_session_secret,
            "LANG": "C",
        }, clear=True):
            clean_env = mgmt_bot._dev_env()
            network_env = mgmt_bot._git_network_env(
                clean_env, self.fixture_token
            )
            git_cmd = mgmt_bot._git_command_with_scoped_credentials(
                ["git", "--version"], network_env
            )
            result = subprocess.run(
                git_cmd,
                capture_output=True,
                text=True,
                env=network_env,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            Path(git_cmd[0]).is_absolute(),
            "authenticated Git must use an absolute executable",
        )
        self.assertNotIn(
            str(planted_bin), network_env["PATH"],
            "authenticated Git PATH must exclude HOME/bin",
        )
        self.assertFalse(
            marker.exists(),
            "HOME/bin planted Git ran or received the synthetic token",
        )

    def test_pull_fetches_with_token_then_merges_without_it(self):
        config = self.project_dir / ".git" / "config"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[remote "origin"]\n\turl = ' + self.clean_url + "\n")
        cmd_file = self._write_command("git_pull", {})
        self._execute(cmd_file, self._fake_git())

        self._assert_no_fixture_credential_in_argv()
        self.assertEqual(
            [self._git_args(argv)[0] for argv, _ in self.calls],
            ["remote", "remote", "fetch", "merge"],
        )

    def test_commit_uses_global_identity_without_inheriting_global_environment(self):
        """A safe read of global identity supports commit without exposing secrets."""
        home = Path(self.tmpdir.name) / "identity-home"
        home.mkdir()
        (home / ".gitconfig").write_text(
            "[user]\n\tname = Fixture Committer\n\temail = fixture@example.test\n"
        )
        self.project_dir.mkdir(parents=True)
        setup_env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
        subprocess.run(
            ["git", "init"], cwd=self.project_dir, env=setup_env,
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", self.clean_url],
            cwd=self.project_dir, env=setup_env, check=True,
            capture_output=True, text=True,
        )
        (self.project_dir / "fixture.txt").write_text("fixture\n")
        cmd_file = self._write_command("git_commit_push", {"message": "fixture commit"})
        calls = []
        real_run = subprocess.run

        def local_with_fake_push(argv, **kwargs):
            argv = list(argv)
            calls.append((argv, kwargs))
            if self._is_git_argv(argv) and self._git_args(argv)[:1] == ["push"]:
                return SimpleNamespace(returncode=0, stdout="pushed", stderr="")
            return real_run(argv, **kwargs)

        with (
            patch.object(mgmt_bot, "STATE_DIR", self.state_dir),
            patch.object(mgmt_bot, "send"),
            patch.object(mgmt_bot.subprocess, "run", side_effect=local_with_fake_push),
            patch.dict(os.environ, {
                "HOME": str(home),
                "GITHUB_TOKEN": self.fixture_token,
                "SESSION_SECRET": self.fixture_session_secret,
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "credential.helper",
                "GIT_CONFIG_VALUE_0": "malicious-fixture-helper",
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
            }, clear=True),
        ):
            mgmt_bot._execute_dev_cmd("telegram-fixture", "1", cmd_file)

        commit = real_run(
            ["git", "log", "-1", "--format=%an <%ae>"],
            cwd=self.project_dir, env=setup_env, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(commit, "Fixture Committer <fixture@example.test>")
        for argv, kwargs in calls:
            child_env = kwargs.get("env", {})
            self.assertFalse(
                "SESSION_SECRET" in child_env or "GIT_CONFIG_COUNT" in child_env,
                "identity/repository subprocess inherited an unsafe environment variable",
            )
            if self._is_git_argv(argv) and self._git_args(argv)[:1] == ["push"]:
                self.assertEqual(child_env.get("GITHUB_TOKEN"), self.fixture_token)
            else:
                self.assertFalse(
                    "GITHUB_TOKEN" in child_env,
                    "only the fake network push may receive the GitHub token",
                )

    def test_local_git_identity_overrides_global_identity_fallback(self):
        home = Path(self.tmpdir.name) / "identity-home"
        home.mkdir()
        (home / ".gitconfig").write_text(
            "[user]\n\tname = Global Fixture\n\temail = global@example.test\n"
        )
        self.project_dir.mkdir(parents=True)
        setup_env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
        subprocess.run(
            ["git", "init"], cwd=self.project_dir, env=setup_env,
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Local Fixture"],
            cwd=self.project_dir, env=setup_env, check=True,
            capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "local@example.test"],
            cwd=self.project_dir, env=setup_env, check=True,
            capture_output=True, text=True,
        )
        with patch.dict(os.environ, {
            "HOME": str(home),
            "PATH": "/usr/bin:/bin",
            "GITHUB_TOKEN": self.fixture_token,
            "SESSION_SECRET": self.fixture_session_secret,
        }, clear=True):
            identity_config = mgmt_bot._git_commit_identity_config(
                self.project_dir, mgmt_bot._dev_env()
            )
        self.assertFalse(
            identity_config,
            "repository-local user.name/email must not be overridden by global identity",
        )

    def test_push_scrubs_legacy_origin_and_redacts_failure_url(self):
        config = self.project_dir / ".git" / "config"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            '[remote "origin"]\n\turl = https://' + self.fixture_token
            + "@github.com/example/private-repo.git\n"
        )
        cmd_file = self._write_command("git_commit_push", {"message": "test"})
        self._execute(
            cmd_file,
            self._fake_git(
                "fatal: could not authenticate to https://"
                + self.fixture_token + "@github.com/example/private-repo.git"
            ),
        )

        self._assert_no_fixture_credential_in_argv()
        origin = config.read_text()
        self.assertIn(self.clean_url, origin)
        self.assertNotIn(self.fixture_token, origin)
        self.assertNotIn(self.fixture_token, "\n".join(self.messages))
        self.assertIn("[REDACTED]", "\n".join(self.messages))

    def test_redactor_masks_url_userinfo_tokens_and_token_query_values(self):
        text = (
            "https://user:password@example.test/path "
            "https://github.com/example/repo?access_token=fixture-value "
            + self.fixture_token
        )
        redacted = mgmt_bot._redact_sensitive_text(text, self.fixture_token)
        self.assertNotIn(self.fixture_token, redacted)
        self.assertNotIn("user:password@", redacted)
        self.assertNotIn("fixture-value", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_scoped_helper_emits_only_github_get_credentials(self):
        """Run the shell helper alone with fixture-only protocol input."""
        helper_env = {
            "GITHUB_TOKEN": self.fixture_token,
            "PATH": "/usr/bin:/bin",
        }

        def invoke(operation, request):
            # Git strips the leading `!` config marker before executing a
            # shell credential helper; invoke that same helper body directly.
            helper_body = mgmt_bot._SCOPED_GIT_CREDENTIAL_HELPER[1:]
            return subprocess.run(
                ["/bin/sh", "-c", helper_body + f" {operation}"],
                input=request,
                capture_output=True,
                text=True,
                check=True,
                env=helper_env,
            ).stdout

        github_output = invoke(
            "get",
            "protocol=https\nhost=github.com\n"
            "path=example/private-repo?access_token=url-fixture-only\n\n",
        )
        self.assertEqual(
            github_output,
            f"username=x-access-token\npassword={self.fixture_token}\n\n",
        )
        self.assertNotIn("url-fixture-only", github_output)
        self.assertEqual(
            invoke("get", "protocol=https\nhost=not-github.example\n\n"),
            "",
        )
        self.assertEqual(
            invoke("store", "protocol=https\nhost=github.com\n\n"),
            "",
        )

    def test_source_uses_a_self_contained_scoped_helper_not_a_token_url(self):
        source = SOURCE.read_text()
        self.assertTrue(
            "_SCOPED_GIT_CREDENTIAL_HELPER" in source,
            "scoped Git credential helper is missing",
        )
        self.assertFalse(
            'f"https://{token_val}@' in source,
            "legacy token interpolation remains in a Git URL",
        )
        self.assertFalse(
            'replace("https://", f"https://{token_val}@")' in source,
            "legacy tokenized origin rewrite remains",
        )


if __name__ == "__main__":
    unittest.main()
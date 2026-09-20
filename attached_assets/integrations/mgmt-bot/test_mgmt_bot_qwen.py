"""Offline tests for the fail-closed management-bot Qwen route."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "mgmt-bot.py"
SPEC = importlib.util.spec_from_file_location("mgmt_bot_qwen", SOURCE)
mgmt_bot = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(mgmt_bot)


def exact_qwen_provider():
    return {
        "baseUrl": "http://192.168.86.46:11434/v1",
        "apiKey": "ollama-local",
        "api": "openai-completions",
        "timeoutSeconds": 1800,
        "models": [{
            "id": "qwen3-coder-131k",
            "name": "qwen3-coder-131k",
            "reasoning": False,
            "input": ["text"],
            "cost": {
                "input": 0,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
            },
            "contextWindow": 16384,
            "maxTokens": 2048,
        }],
    }


def config_with_qwen():
    return {
        "models": {
            "providers": {
                "custom-mac-ollama": exact_qwen_provider(),
            },
        },
        "agents": {
            "defaults": {
                "model": {
                    "primary": "openai-codex/gpt-5.6-terra",
                    "fallbacks": ["anthropic/claude-sonnet-5"],
                },
                "providerTimeoutSeconds": {
                    "custom-mac-ollama": 1800,
                },
            },
            "list": [{
                "id": "main",
                "model": {
                    "primary": "openai-codex/gpt-5.6-terra",
                    "fallbacks": ["anthropic/claude-sonnet-5"],
                },
            }],
        },
    }


class QwenManagementBotTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmpdir.name) / ".openclaw"
        self.config_path = self.state_dir / "openclaw.json"
        self.state_dir.mkdir()
        self.original_config = config_with_qwen()
        self.config_path.write_text(json.dumps(self.original_config))
        self.messages = []
        self.restarts = []
        self.env = {
            "OPENCLAW_CONFIG_PATH": str(self.config_path),
            "OPENCLAW_STATE_DIR": str(self.state_dir),
            "OPENCLAW_SERVICE_NAME": "openclaw-gateway.service",
            "OPENCLAW_LOCAL_QWEN30B_MODEL": (
                "custom-mac-ollama/qwen3-coder-131k"
            ),
        }

    def tearDown(self):
        self.tmpdir.cleanup()

    def _boundary_patches(self):
        return patch.object(
            mgmt_bot,
            "MAC_QWEN_PRIMARY_STATE_DIR",
            self.state_dir,
        ), patch.object(
            mgmt_bot,
            "MAC_QWEN_PRIMARY_CONFIG_PATH",
            self.config_path,
        )

    def test_verifier_requires_exact_provider_and_openclaw_sentinel(self):
        responses = [
            {"models": [{"name": "qwen3-coder-131k:latest"}]},
            {"data": [{"id": "qwen3-coder-131k"}]},
        ]
        with (
            self._boundary_patches()[0],
            self._boundary_patches()[1],
            patch.dict(os.environ, self.env, clear=True),
            patch.object(mgmt_bot, "_qwen_http_json", side_effect=responses),
            patch.object(
                mgmt_bot,
                "_qwen_openclaw_probe",
                return_value=(True, "QWEN-LOCAL-OK"),
            ) as probe,
        ):
            ok, detail = mgmt_bot._verify_qwen_route(self.original_config)

        self.assertTrue(ok, detail)
        self.assertEqual(detail, "QWEN-LOCAL-OK")
        probe.assert_called_once()

    def test_openclaw_probe_reports_redacted_failure_detail(self):
        with patch.object(
            mgmt_bot.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=7,
                stdout="",
                stderr="provider custom-mac-ollama apiKey=secret-value",
            ),
        ):
            ok, detail = mgmt_bot._qwen_openclaw_probe(Path("/tmp/qwen-probe.json"))

        self.assertFalse(ok)
        self.assertIn("exit=7", detail)
        self.assertIn("apiKey=[redacted]", detail)
        self.assertNotIn("secret-value", detail)

    def test_wrong_qwen_override_is_rejected_without_write_or_restart(self):
        self.env["OPENCLAW_LOCAL_QWEN30B_MODEL"] = "openai/gpt-5.6"
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(mgmt_bot, "_write_config") as write_config,
            patch.object(mgmt_bot, "_restart_gateway") as restart,
            patch.object(
                mgmt_bot,
                "send",
                side_effect=lambda _token, _chat, text: self.messages.append(text),
            ),
        ):
            mgmt_bot.cmd_switch("token", "chat", "qwen30b")

        write_config.assert_not_called()
        restart.assert_not_called()
        self.assertIn("exact approved route", "\n".join(self.messages))
        self.assertEqual(
            mgmt_bot._get_current_model(json.loads(self.config_path.read_text())),
            "openai-codex/gpt-5.6-terra",
        )

    def test_failed_qwen_verification_preserves_existing_default(self):
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(
                mgmt_bot,
                "_verify_qwen_route",
                return_value=(False, "Mac Mini sentinel failed"),
            ),
            patch.object(mgmt_bot, "_write_config") as write_config,
            patch.object(mgmt_bot, "_restart_gateway") as restart,
            patch.object(
                mgmt_bot,
                "send",
                side_effect=lambda _token, _chat, text: self.messages.append(text),
            ),
        ):
            mgmt_bot.cmd_switch("token", "chat", "qwen30b")

        write_config.assert_not_called()
        restart.assert_not_called()
        self.assertIn("activation blocked", "\n".join(self.messages))
        self.assertEqual(
            mgmt_bot._get_current_model(json.loads(self.config_path.read_text())),
            "openai-codex/gpt-5.6-terra",
        )

    def test_successful_qwen_swap_writes_then_restarts_primary_gateway(self):
        written = {}

        def capture_write(config):
            written.update(config)
            self.config_path.write_text(json.dumps(config))

        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(
                mgmt_bot,
                "_verify_qwen_route",
                return_value=(True, "QWEN-LOCAL-OK"),
            ) as verifier,
            patch.object(mgmt_bot, "_write_config", side_effect=capture_write),
            patch.object(
                mgmt_bot,
                "_restart_gateway",
                side_effect=lambda: (
                    self.restarts.append("openclaw-gateway.service")
                    or (True, "Gateway restarted successfully")
                ),
            ),
            patch.object(mgmt_bot, "_service_status", return_value="active"),
            patch.object(
                mgmt_bot,
                "send",
                side_effect=lambda _token, _chat, text: self.messages.append(text),
            ),
        ):
            mgmt_bot.cmd_switch("token", "chat", "qwen30b")

        self.assertEqual(
            mgmt_bot._get_current_model(written),
            "custom-mac-ollama/qwen3-coder-131k",
        )
        verifier.assert_called_once()
        self.assertEqual(self.restarts, ["openclaw-gateway.service"])
        self.assertIn("Model set to custom-mac-ollama/qwen3-coder-131k", "\n".join(self.messages))


if __name__ == "__main__":
    unittest.main()
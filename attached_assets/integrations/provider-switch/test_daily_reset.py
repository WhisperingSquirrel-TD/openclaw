"""Offline tests for the overnight exclusive model reset."""

import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "daily-reset.py"
SPEC = importlib.util.spec_from_file_location("daily_reset", SOURCE)
daily_reset = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(daily_reset)


class DailyResetTests(unittest.TestCase):
    def test_reset_updates_defaults_and_all_agent_routes_without_fallbacks(self):
        config = {
            "agents": {
                "defaults": {
                    "model": {
                        "primary": "custom-mac-ollama/qwen3-coder-131k",
                        "fallbacks": ["openai-codex/gpt-5.6-terra"],
                    },
                },
                "list": [{
                    "id": "main",
                    "model": {
                        "primary": "custom-mac-ollama/qwen3-coder-131k",
                        "fallbacks": ["openai-codex/gpt-5.6-terra"],
                    },
                }],
            },
        }

        daily_reset._set_model(config, "openai-codex/gpt-5.6-terra")

        self.assertEqual(
            config["agents"]["defaults"]["model"],
            {"primary": "openai-codex/gpt-5.6-terra", "fallbacks": []},
        )
        self.assertEqual(
            config["agents"]["list"][0]["model"],
            {"primary": "openai-codex/gpt-5.6-terra", "fallbacks": []},
        )


if __name__ == "__main__":
    unittest.main()
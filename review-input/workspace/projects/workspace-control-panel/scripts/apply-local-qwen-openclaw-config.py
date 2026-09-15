#!/usr/bin/env python3
"""Apply the protected OpenClaw config changes for Mac mini Qwen 131k.

This script is intentionally narrow and idempotent. It updates ~/.openclaw/openclaw.json
with:
- auth profile custom-mac-ollama:default
- provider custom-mac-ollama at http://192.168.86.46:11434/v1
- model custom-mac-ollama/qwen3-coder-131k alias qwen-coder30b
- removes the old failed/stale custom-192-168-86-45-11434 route if present

It does not switch the main primary model to local Qwen.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG = Path.home() / ".openclaw" / "openclaw.json"


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

    auth_profiles = cfg.setdefault("auth", {}).setdefault("profiles", {})
    auth_profiles["custom-mac-ollama:default"] = {
        "provider": "custom-mac-ollama",
        "mode": "api_key",
    }

    providers = cfg.setdefault("models", {}).setdefault("providers", {})
    providers["custom-mac-ollama"] = {
        "baseUrl": "http://192.168.86.46:11434/v1",
        "apiKey": "ollama",
        "api": "openai-completions",
        "models": [
            {
                "id": "qwen3-coder-131k",
                "name": "qwen3-coder-131k (Mac mini Ollama, 131072 ctx)",
                "reasoning": False,
                "input": ["text"],
                "cost": {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                },
                "contextWindow": 131072,
                "maxTokens": 8192,
            }
        ],
    }

    # Remove the old failed/stale provider route from active config if present.
    auth_profiles.pop("custom-192-168-86-45-11434:default", None)
    providers.pop("custom-192-168-86-45-11434", None)

    default_models = cfg.setdefault("agents", {}).setdefault("defaults", {}).setdefault("models", {})
    default_models.pop("custom-192-168-86-45-11434/qwen3-coder:30b", None)
    default_models["custom-mac-ollama/qwen3-coder-131k"] = {"alias": "qwen-coder30b"}

    defaults = cfg.setdefault("agents", {}).setdefault("defaults", {})
    compaction = defaults.setdefault("compaction", {})
    compaction["reserveTokensFloor"] = 20000

    # Safety: never change the main primary model here.
    primary = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary")
    if primary == "custom-mac-ollama/qwen3-coder-131k":
        cfg["agents"]["defaults"]["model"]["primary"] = "openai-codex/gpt-5.5"

    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    tmp.replace(CONFIG)
    print("OK: custom-mac-ollama/qwen3-coder-131k configured; main primary left on cloud model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

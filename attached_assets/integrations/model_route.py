"""Shared exclusive model-route helpers for the Pi management jobs.

The gateway has three independent places where a generation model can survive a
switch: the global default, per-agent config, and persisted session state. Keep
all three aligned when the operator selects a route.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SESSION_MODEL_FIELDS = (
    "modelOverride",
    "providerOverride",
    "model",
    "modelProvider",
)


def _model_config(current: Any, model: str) -> dict[str, Any]:
    value = dict(current) if isinstance(current, dict) else {}
    value["primary"] = model
    # A provider fallback is another live route. Route switches are deliberately
    # fail-closed: if the selected provider fails, do not silently call Terra or
    # Ollama behind the operator's back.
    value["fallbacks"] = []
    return value


def apply_exclusive_model(config: dict[str, Any], model: str) -> dict[str, Any]:
    """Set one generation route across defaults and configured agents."""
    agents = config.setdefault("agents", {})
    if not isinstance(agents, dict):
        agents = {}
        config["agents"] = agents

    defaults = agents.setdefault("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
        agents["defaults"] = defaults
    defaults["model"] = _model_config(defaults.get("model"), model)

    entries = agents.get("list")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry["model"] = _model_config(entry.get("model"), model)

    # Support the older config shape used by some installed OpenClaw versions.
    legacy_agent = config.get("agent")
    if isinstance(legacy_agent, dict):
        legacy_agent["model"] = model

    return config


def _session_store_paths(state_dir: Path) -> list[Path]:
    root = state_dir.expanduser().resolve()
    candidates = [root / "sessions.json"]
    agents_dir = root / "agents"
    if agents_dir.is_dir():
        candidates.extend(agents_dir.glob("*/sessions/sessions.json"))

    paths: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (FileNotFoundError, OSError, ValueError):
            continue
        if resolved.is_file() and resolved not in paths:
            paths.append(resolved)
    return sorted(paths)


def clear_session_model_routes(state_dir: Path) -> tuple[int, int]:
    """Remove persisted model selections while preserving session history.

    Returns (files_changed, entries_changed). The gateway should be restarted
    immediately after this operation so its in-memory session cache cannot
    continue using the old route.
    """
    files_changed = 0
    entries_changed = 0

    for path in _session_store_paths(state_dir):
        try:
            store = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(store, dict):
            continue

        changed = False
        for entry in store.values():
            if not isinstance(entry, dict):
                continue
            entry_changed = False
            for field in SESSION_MODEL_FIELDS:
                if field in entry:
                    del entry[field]
                    entry_changed = True
            if entry_changed:
                entries_changed += 1
                changed = True

        if not changed:
            continue

        mode = path.stat().st_mode & 0o777
        tmp = path.with_name(f".{path.name}.route-tmp-{os.getpid()}")
        try:
            tmp.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
            os.chmod(tmp, mode)
            os.replace(tmp, path)
            files_changed += 1
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    return files_changed, entries_changed


def session_model_routes(state_dir: Path) -> dict[str, int]:
    """Return persisted session routes without exposing session identities."""
    routes: dict[str, int] = {}
    for path in _session_store_paths(state_dir):
        try:
            store = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(store, dict):
            continue
        for entry in store.values():
            if not isinstance(entry, dict):
                continue
            provider = str(entry.get("providerOverride") or entry.get("modelProvider") or "").strip()
            model = str(entry.get("modelOverride") or entry.get("model") or "").strip()
            if not model:
                continue
            route = f"{provider}/{model}" if provider and "/" not in model else model
            routes[route] = routes.get(route, 0) + 1
    return routes
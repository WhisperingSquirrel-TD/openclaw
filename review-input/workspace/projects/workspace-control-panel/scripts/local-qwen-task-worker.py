#!/usr/bin/env python3
"""
Local Qwen task worker adapter.

Runs a bounded task-system execution packet against the Mac mini Ollama route.
This is deliberately NOT a general OpenClaw session runner: it accepts a compact
packet, asks Qwen for a structured local-worker-result-v1 response, and prints JSON.

Environment overrides:
  LOCAL_QWEN_BASE_URL   default http://192.168.86.46:11434
  LOCAL_QWEN_MODEL      default qwen3-coder-131k
  LOCAL_QWEN_TIMEOUT_S  default 180
  LOCAL_QWEN_NUM_CTX    default 131072

Usage:
  scripts/local-qwen-task-worker.py packet.json
  cat packet.json | scripts/local-qwen-task-worker.py -
  scripts/local-qwen-task-worker.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("LOCAL_QWEN_BASE_URL", "http://192.168.86.46:11434").rstrip("/")
MODEL = os.environ.get("LOCAL_QWEN_MODEL", "qwen3-coder-131k")
TIMEOUT = int(os.environ.get("LOCAL_QWEN_TIMEOUT_S", "180"))
NUM_CTX = int(os.environ.get("LOCAL_QWEN_NUM_CTX", "131072"))

RESULT_SCHEMA = {
    "schema": "local-worker-result-v1",
    "status": "completed | needs_context | refused | failed",
    "confidence": "low | medium | high",
    "used_context_refs": ["string"],
    "output": {"type": "draft | summary | classification | transformation | none", "content": "string"},
    "missing_context_requests": [
        {
            "type": "crm_summary | sharepoint_artifact | email_thread | file | task_timeline | exclusions_register | other",
            "ref_or_description": "string",
            "why_needed": "string",
            "blocks_completion": True,
        }
    ],
    "assumptions": ["string"],
    "verification_notes_for_orchestrator": ["string"],
    "should_not_write_back_directly": True,
}

SYSTEM_PROMPT = """You are a bounded local task worker for Tom's Workspace Control Panel.
You are cheap, private, and waitable, but you are not the source of truth.

Hard rules:
- Work only from the supplied packet. Do not invent missing business facts.
- Do not claim to have read files, CRM, SharePoint, inboxes, calendars, or the web.
- Do not send messages, update external systems, or make final high-risk decisions.
- If required context is missing, return needs_context with specific missing items.
- If the task is external-facing, high-risk, broad-discovery, or unsuitable for local execution, return refused.
- Return ONLY valid JSON matching local-worker-result-v1. No markdown, no prose wrapper.
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _failure(status: str, message: str, *, packet: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "local-worker-result-v1",
        "status": status,
        "confidence": "low",
        "used_context_refs": [],
        "output": {"type": "none", "content": ""},
        "missing_context_requests": [],
        "assumptions": [],
        "verification_notes_for_orchestrator": [message],
        "should_not_write_back_directly": True,
        "adapter": {
            "model": MODEL,
            "base_url": BASE_URL,
            "num_ctx": NUM_CTX,
            "created_at": _now(),
            "subtask_id": (packet or {}).get("subtask_id"),
        },
    }


def _load_packet(path: str) -> dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    packet = json.loads(raw)
    if not isinstance(packet, dict):
        raise ValueError("packet must be a JSON object")
    return packet


def _validate_packet(packet: dict[str, Any]) -> None:
    required = ["packet_version", "task_id", "subtask_id", "title", "next_action", "success_definition", "risk", "execution_mode", "routing_class"]
    missing = [k for k in required if not packet.get(k)]
    if missing:
        raise ValueError(f"packet missing required fields: {', '.join(missing)}")
    if packet.get("routing_class") != "local_ready":
        raise ValueError(f"packet routing_class must be local_ready, got {packet.get('routing_class')!r}")
    if packet.get("risk") == "HIGH":
        raise ValueError("HIGH-risk packets are never local-worker eligible")


def _call_ollama(packet: dict[str, Any]) -> dict[str, Any]:
    user_prompt = {
        "instruction": "Complete the supplied local-ready task packet or return needs_context/refused. Return only JSON.",
        "required_return_schema": RESULT_SCHEMA,
        "packet": packet,
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        "stream": False,
        "format": "json",
        "options": {"num_ctx": NUM_CTX, "temperature": 0.2},
    }
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    content = ((raw.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError(f"Ollama returned empty content: {raw}")
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"worker returned malformed JSON: {exc}: {content[:1000]}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("worker result was not a JSON object")
    result.setdefault("schema", "local-worker-result-v1")
    result.setdefault("should_not_write_back_directly", True)
    result["adapter"] = {
        "model": MODEL,
        "base_url": BASE_URL,
        "num_ctx": NUM_CTX,
        "created_at": _now(),
        "subtask_id": packet.get("subtask_id"),
    }
    return result


def _self_test_packet() -> dict[str, Any]:
    return {
        "packet_version": "local-task-worker-v1",
        "task_id": "self-test-task",
        "subtask_id": "self-test-subtask",
        "title": "Local worker self-test",
        "intent": "Prove the Mac mini Qwen route can return structured JSON.",
        "next_action": "Return a one-sentence summary saying the local worker route is alive.",
        "success_definition": "Valid local-worker-result-v1 JSON with status completed and a short summary output.",
        "risk": "LOW",
        "execution_mode": "do_now",
        "routing_class": "local_ready",
        "provided_context": [
            {
                "label": "Self-test instruction",
                "source_kind": "task",
                "source_ref": "self-test",
                "content": "This is a synthetic local worker health check. No external facts are required.",
                "truth_status": "verified",
            }
        ],
        "source_of_truth": [
            {"topic": "self-test", "primary_source_ref": "self-test", "worker_instruction": "treat as authoritative"}
        ],
        "constraints": ["Return JSON only", "Do not claim external access"],
        "known_gaps": [],
        "stop_if_missing": [],
        "allowed_output_types": ["summary", "refusal"],
        "required_return_schema": "local-worker-result-v1",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", nargs="?", help="packet JSON path, or - for stdin")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    try:
        packet = _self_test_packet() if args.self_test else _load_packet(args.packet or "-")
        _validate_packet(packet)
        result = _call_ollama(packet)
    except (urllib.error.URLError, TimeoutError) as exc:
        result = _failure("failed", f"local Qwen route unavailable or timed out: {exc}")
    except Exception as exc:
        result = _failure("failed", str(exc))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"completed", "needs_context", "refused"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

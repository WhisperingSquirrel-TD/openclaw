#!/usr/bin/env python3
"""Emit a compact summary of OpenClaw sessions.json without dumping the registry."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--path", type=Path, required=True)
    p.add_argument("--max-sessions", type=int, default=100)
    args = p.parse_args()
    try:
        data = json.loads(args.path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2
    rows = []
    if isinstance(data, dict):
        iterable = data.items()
    elif isinstance(data, list):
        iterable = ((item.get("key", ""), item) for item in data if isinstance(item, dict))
    else:
        iterable = []
    for key, item in iterable:
        if not isinstance(item, dict):
            continue
        rows.append({
            "key": key,
            "model": item.get("model") or item.get("modelId"),
            "context_window": item.get("contextTokens") or item.get("contextWindow"),
            "total_tokens": item.get("totalTokens"),
            "input_tokens": item.get("inputTokens"),
            "output_tokens": item.get("outputTokens"),
            "compaction_count": item.get("compactionCount", 0),
            "updated": item.get("updatedAt") or item.get("updated"),
        })
        if len(rows) >= args.max_sessions:
            break
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

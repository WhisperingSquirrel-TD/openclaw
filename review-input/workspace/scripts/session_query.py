#!/usr/bin/env python3
"""Search OpenClaw JSONL sessions and return bounded matching snippets."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterator


DEFAULT_MAX_FILES = 50
DEFAULT_MAX_FILE_BYTES = 25_000_000
DEFAULT_MAX_TOTAL_CHARS = 12_000


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def text_values(value: Any) -> Iterator[str]:
    """Yield human-readable message fields, excluding accounting metadata."""
    if isinstance(value, str):
        if value.strip():
            yield value
    elif isinstance(value, list):
        for item in value:
            yield from text_values(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in {"usage", "cost", "toolCallId", "parentId", "partialJson"}:
                yield from text_values(item)


def files_for(path: Path, max_files: int, max_file_bytes: int) -> tuple[list[Path], list[str]]:
    candidates = [path] if path.is_file() else sorted(path.rglob("*.jsonl")) if path.is_dir() else []
    accepted: list[Path] = []
    skipped: list[str] = []
    for candidate in candidates:
        try:
            size = candidate.stat().st_size
        except OSError:
            skipped.append(f"unstatable:{candidate}")
            continue
        if size > max_file_bytes:
            skipped.append(f"too_large:{candidate}")
            continue
        if len(accepted) >= max_files:
            skipped.append("file_limit_reached")
            break
        accepted.append(candidate)
    return accepted, skipped


def bounded_snippet(text: str, match: re.Match[str], snippet_chars: int) -> str:
    half = max(100, snippet_chars // 2)
    start = max(0, match.start() - half)
    end = min(len(text), start + snippet_chars)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("query")
    parser.add_argument("--regex", action="store_true")
    parser.add_argument("--max-matches", type=positive, default=20)
    parser.add_argument("--snippet-chars", type=positive, default=1000)
    parser.add_argument("--max-files", type=positive, default=DEFAULT_MAX_FILES)
    parser.add_argument("--max-file-bytes", type=positive, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-total-chars", type=positive, default=DEFAULT_MAX_TOTAL_CHARS)
    args = parser.parse_args()
    pattern = re.compile(args.query, re.I) if args.regex else re.compile(re.escape(args.query), re.I)
    files, skipped = files_for(args.path, args.max_files, args.max_file_bytes)
    results: list[dict[str, Any]] = []
    emitted = 0
    truncated = False

    for file in files:
        try:
            handle = file.open(encoding="utf-8", errors="replace")
        except OSError:
            skipped.append(f"unreadable:{file}")
            continue
        with handle:
            for line_number, raw in enumerate(handle, 1):
                if len(results) >= args.max_matches:
                    truncated = True
                    break
                # Avoid decoding/traversing a giant record unless it plausibly matches.
                if not pattern.search(raw):
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                message = record.get("message", record) if isinstance(record, dict) else record
                # Cap constructed text: a match has already been found in raw JSON.
                # The cap is character-based so one giant tool-result field cannot expand
                # in memory merely because it counts as a single yielded value.
                text_parts: list[str] = []
                remaining = args.snippet_chars * 4
                for part in text_values(message):
                    if remaining <= 0:
                        break
                    piece = part[:remaining]
                    text_parts.append(piece)
                    remaining -= len(piece)
                text = "\n".join(text_parts)
                match = pattern.search(text)
                if not match:
                    continue
                row = {
                    "file": str(file), "line": line_number,
                    "record_type": record.get("type") if isinstance(record, dict) else None,
                    "id": record.get("id") if isinstance(record, dict) else None,
                    "timestamp": record.get("timestamp") if isinstance(record, dict) else None,
                    "role": message.get("role") if isinstance(message, dict) else None,
                    "snippet": bounded_snippet(text, match, args.snippet_chars),
                }
                candidate_size = len(json.dumps(row, ensure_ascii=False))
                if emitted + candidate_size > args.max_total_chars:
                    truncated = True
                    break
                results.append(row)
                emitted += candidate_size
        if truncated:
            break
    print(json.dumps({
        "matches": results,
        "match_count": len(results),
        "truncated": truncated,
        "skipped": skipped,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

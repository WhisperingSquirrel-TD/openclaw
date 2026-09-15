#!/usr/bin/env python3
"""Extract bounded, targeted slices from one or more text files.

Default limits apply to the whole invocation, not separately to every path.
Use --full only when the raw material itself is intentionally required.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def section_lines(lines: list[str], heading: str) -> list[tuple[int, str]]:
    wanted = heading.strip().lstrip("#").strip().casefold()
    start = None
    level = 0
    for index, line in enumerate(lines):
        match = re.match(r"^(#+)\s+(.*)$", line)
        if match and match.group(2).strip().casefold() == wanted:
            start, level = index + 1, len(match.group(1))
            break
    if start is None:
        return []
    end = len(lines)
    for index in range(start, len(lines)):
        match = re.match(r"^(#+)\s+", lines[index])
        if match and len(match.group(1)) <= level:
            end = index
            break
    return [(index + 1, lines[index]) for index in range(start, end)]


def emit(text: str, remaining: int) -> tuple[int, bool]:
    if remaining <= 0:
        return 0, True
    if len(text) <= remaining:
        print(text, end="")
        return len(text), False
    print(text[:remaining], end="")
    return remaining, True


def print_block(items: list[tuple[int, str]], remaining: int) -> tuple[int, bool]:
    used = 0
    for number, line in items:
        consumed, truncated = emit(f"{number}: {line}\n", remaining - used)
        used += consumed
        if truncated:
            return used, True
    return used, False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--section")
    parser.add_argument("--match", help="regular expression matched against lines")
    parser.add_argument("--before", type=nonnegative, default=0)
    parser.add_argument("--after", type=nonnegative, default=0)
    parser.add_argument("--max-chars", type=positive, default=12000,
                        help="total default output limit for this invocation")
    parser.add_argument("--full", action="store_true", help="intentional unbounded output")
    args = parser.parse_args()
    regex = re.compile(args.match, re.I) if args.match else None
    remaining = args.max_chars

    for path in args.paths:
        if args.full:
            print(f"# {path}")
            try:
                print(path.read_text(encoding="utf-8", errors="replace"), end="")
            except OSError as exc:
                print(f"[unreadable: {exc}]")
            continue
        consumed, exhausted = emit(f"# {path}\n", remaining)
        remaining -= consumed
        if exhausted:
            print("\n[output truncated at invocation limit]")
            return 0
        if not path.exists():
            consumed, _ = emit("[missing]\n", remaining)
            remaining -= consumed
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            consumed, _ = emit(f"[unreadable: {exc}]\n", remaining)
            remaining -= consumed
            continue
        if args.section:
            selected = section_lines(lines, args.section)
            if not selected:
                consumed, _ = emit("[section not found]\n", remaining)
                remaining -= consumed
                continue
        elif regex:
            indexes = [index for index, line in enumerate(lines) if regex.search(line)]
            selected_indexes: set[int] = set()
            for index in indexes:
                selected_indexes.update(range(max(0, index - args.before), min(len(lines), index + args.after + 1)))
            selected = [(index + 1, lines[index]) for index in sorted(selected_indexes)]
            if not selected:
                consumed, _ = emit("[no matches]\n", remaining)
                remaining -= consumed
                continue
        else:
            selected = [(index + 1, line) for index, line in enumerate(lines)]
        consumed, exhausted = print_block(selected, remaining)
        remaining -= consumed
        if exhausted:
            print("\n[output truncated at invocation limit]")
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

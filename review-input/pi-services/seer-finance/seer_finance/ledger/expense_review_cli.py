"""CLI for a new, read-only SEER expense review snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .expense_review_tray import _FORBIDDEN_ACTIONS, build_review_snapshot


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Build a read-only SEER expense review snapshot.")
    value.add_argument("--manifest", required=True, help="existing dry-run manifest JSON (read only)")
    value.add_argument("--output", required=True, help="new caller-specified review snapshot JSON")
    return value


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg in _FORBIDDEN_ACTIONS or any(arg.startswith(flag + "=") for flag in _FORBIDDEN_ACTIONS) for arg in argv):
        print("refused: review snapshots are read-only; --apply/--write/--cutover/--action are not supported", file=sys.stderr)
        return 2
    args = parser().parse_args(argv)
    output = Path(args.output)
    if output.exists():
        print("refused: output must be a new review snapshot path", file=sys.stderr)
        return 2
    snapshot = build_review_snapshot(Path(args.manifest))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

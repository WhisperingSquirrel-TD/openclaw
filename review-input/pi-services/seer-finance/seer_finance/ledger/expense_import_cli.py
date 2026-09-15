"""Command line entry point for the non-destructive Phase 2 manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .expense_importer import build_manifest


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description="Build a SEER expense dry-run reconciliation manifest.")
    argument_parser.add_argument("--transactions", required=True, help="existing transactions.json (read only)")
    argument_parser.add_argument("--expenses-markdown", required=True, help="existing seer-expenses.md (read only)")
    argument_parser.add_argument("--queue", required=True, help="existing enrichment queue JSON (read only)")
    argument_parser.add_argument("--tide-reconciliation", help="optional Tide reconciliation markdown evidence (read only)")
    argument_parser.add_argument("--output", required=True, help="caller-provided manifest output path")
    argument_parser.add_argument("--dry-run", action="store_true", default=True, help="required mode; retained for explicit invocation")
    argument_parser.add_argument("--write", "--cutover", "--apply", action="store_true", help=argparse.SUPPRESS)
    return argument_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.write:
        parser().error("non-dry-run modes are refused: this importer never writes ledger data or performs cutover")
    output = Path(args.output)
    # Only the explicitly supplied report location is writable by this CLI.
    manifest = build_manifest(args.transactions, args.expenses_markdown, args.queue, args.tide_reconciliation)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

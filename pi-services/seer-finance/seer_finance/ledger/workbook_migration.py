"""Local migration from structured Markdown and historical XLSX ledgers.

The migration intentionally writes ordinary local files only.  It never queues
or mutates SharePoint; an operator must separately review and submit the
resulting workbook through the normal base-checked transport.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .sharepoint_contract import parse_document
from .workbook_codec import (
    WorkbookCodec,
    WorkbookCodecError,
    encode_expense_workbook,
    encode_finance_workbook,
)


class WorkbookMigrationError(ValueError):
    """A migration source cannot be safely converted without data loss."""


_LIST_KEYS = {
    "expense": ("expenses", "events", "collisions", "evidence"),
    "finance": ("transactions",),
}
_IDENTITY_KEYS = {
    "expenses": ("expense_id", "source_ref"),
    "events": ("event_id",),
    "collisions": ("collision_id",),
    "evidence": ("evidence_id",),
    "transactions": ("txn_id", "source_ref"),
}
_TIME_KEYS = ("updated_at", "occurred_at", "created_at", "observed_timestamp", "date")


def _load_markdown(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise WorkbookMigrationError(f"cannot read Markdown source {source}: {exc}") from exc
    try:
        value = parse_document(content, path=str(source))
    except Exception as exc:
        # Accept a raw JSON object as a convenience for old exported sources,
        # while retaining strict object validation.
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            raise WorkbookMigrationError(f"invalid structured Markdown source {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkbookMigrationError(f"structured source {source} must contain an object")
    return value


def _load_workbook(path: str | Path, kind: str) -> dict[str, Any]:
    source = Path(path)
    try:
        content = source.read_bytes()
    except OSError as exc:
        raise WorkbookMigrationError(f"cannot read historical workbook {source}: {exc}") from exc
    try:
        return WorkbookCodec.decode(content, kind=kind)
    except WorkbookCodecError as exc:
        raise WorkbookMigrationError(f"invalid historical workbook {source}: {exc}") from exc


def _record_identity(record: Mapping[str, Any], key: str) -> tuple[str, str] | None:
    for identity_key in _IDENTITY_KEYS.get(key, ()):
        value = record.get(identity_key)
        if isinstance(value, str) and value:
            return identity_key, value
    return None


def _time_key(record: Mapping[str, Any]) -> str:
    for key in _TIME_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _merge_record(preferred: Mapping[str, Any], historical: Mapping[str, Any]) -> dict[str, Any]:
    """Keep latest values while filling absent values from old evidence."""
    result = dict(preferred)
    for key, value in historical.items():
        if key not in result or result[key] is None:
            result[key] = value
    return result


def merge_ledger_sources(
    sources: Iterable[Mapping[str, Any]], *, kind: str
) -> dict[str, Any]:
    """Merge latest structured source first, then historical sources.

    Existing rows are identity-deduplicated but never discarded merely because
    one source lacks a field.  The first source is treated as the latest source
    (the CLI places Markdown before historical workbooks); its non-null values
    win while older values fill gaps.
    """
    if kind not in _LIST_KEYS:
        raise WorkbookMigrationError(f"unknown ledger kind {kind!r}")
    materialized = list(sources)
    if not materialized:
        raise WorkbookMigrationError("at least one migration source is required")
    result: dict[str, Any] = {"schema_version": 1}
    for source in materialized:
        if not isinstance(source, Mapping):
            raise WorkbookMigrationError("migration source must be an object")
        if source.get("schema_version") not in (None, 1):
            raise WorkbookMigrationError("only schema_version 1 sources can be migrated")
        if result.get("schema_version") == 1 and isinstance(source.get("schema_version"), int):
            result["schema_version"] = source["schema_version"]
        for key, value in source.items():
            if key == "schema_version" or isinstance(value, list):
                continue
            if key not in result or result[key] is None:
                result[key] = value
    for key in _LIST_KEYS[kind]:
        rows: list[dict[str, Any]] = []
        positions: dict[tuple[str, str], int] = {}
        # Iterate newest source first.  Historical-only rows are appended in
        # source order, preserving an auditable chronology.
        for source in materialized:
            incoming = source.get(key, [])
            if not isinstance(incoming, list):
                raise WorkbookMigrationError(f"{key} must be a list in every migration source")
            for row in incoming:
                if not isinstance(row, Mapping):
                    raise WorkbookMigrationError(f"{key} rows must be objects")
                identity = _record_identity(row, key)
                if identity is None:
                    # Do not invent an identity for an evidence/event row.  A
                    # complete copy is safer than accidental deduplication.
                    rows.append(dict(row))
                    continue
                if identity not in positions:
                    positions[identity] = len(rows)
                    rows.append(dict(row))
                else:
                    index = positions[identity]
                    existing = rows[index]
                    # Source order is authoritative.  If an older source has a
                    # newer explicit timestamp, its fields become preferred,
                    # while the other row still contributes absent fields.
                    if _time_key(row) > _time_key(existing):
                        rows[index] = _merge_record(row, existing)
                    else:
                        rows[index] = _merge_record(existing, row)
        result[key] = rows
    return result


def migrate_sources(
    *,
    kind: str,
    markdown: str | Path | None = None,
    historical_workbooks: Iterable[str | Path] = (),
    output: str | Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Build one workbook locally and return an auditable migration report."""
    sources: list[Mapping[str, Any]] = []
    source_names: list[str] = []
    if markdown is not None:
        sources.append(_load_markdown(markdown))
        source_names.append(str(markdown))
    for historical in historical_workbooks:
        sources.append(_load_workbook(historical, kind))
        source_names.append(str(historical))
    merged = merge_ledger_sources(sources, kind=kind)
    content = encode_expense_workbook(merged) if kind == "expense" else encode_finance_workbook(merged)
    report: dict[str, Any] = {
        "kind": kind,
        "sources": source_names,
        "rows": {key: len(merged[key]) for key in _LIST_KEYS[kind]},
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "semantic_workbook_sha256": WorkbookCodec.semantic_hash(content, kind=kind),
        "semantic_sha256": WorkbookCodec.semantic_hash(content, kind=kind),
        "bytes": len(content),
        "applied": False,
    }
    if output is not None and apply:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        report["output"] = str(destination)
        report["applied"] = True
    elif output is not None:
        report["output"] = str(output)
        report["note"] = "dry run; no local workbook written (use --apply)"
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build authoritative-format XLSX ledgers from structured Markdown and historical workbooks"
    )
    parser.add_argument("--expense-markdown")
    parser.add_argument("--finance-markdown")
    parser.add_argument("--expense-excel", action="append", default=[])
    parser.add_argument("--finance-excel", action="append", default=[])
    parser.add_argument("--expense-output", default="Expenses/Expense ledger.xlsx")
    parser.add_argument("--finance-output", default="Finance/Finance ledger.xlsx")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write local output files; never mutates SharePoint",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    reports: list[dict[str, Any]] = []
    if args.expense_markdown or args.expense_excel:
        reports.append(
            migrate_sources(
                kind="expense",
                markdown=args.expense_markdown,
                historical_workbooks=args.expense_excel,
                output=args.expense_output,
                apply=args.apply,
            )
        )
    if args.finance_markdown or args.finance_excel:
        reports.append(
            migrate_sources(
                kind="finance",
                markdown=args.finance_markdown,
                historical_workbooks=args.finance_excel,
                output=args.finance_output,
                apply=args.apply,
            )
        )
    if not reports:
        _parser().error("provide at least one Markdown or historical Excel source")
    print(json.dumps({"migrations": reports}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

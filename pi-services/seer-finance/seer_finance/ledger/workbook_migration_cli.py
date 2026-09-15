"""Command-line entry point for the local XLSX migration."""

from __future__ import annotations

from .workbook_migration import main


if __name__ == "__main__":
    raise SystemExit(main())

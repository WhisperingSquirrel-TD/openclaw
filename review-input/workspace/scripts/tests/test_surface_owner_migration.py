#!/usr/bin/env python3
"""Focused regression test for continuity source-owner migration."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "inbound-monitoring.py"
spec = importlib.util.spec_from_file_location("inbound_monitoring", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "ASSISTANT_INBOX.md"
        now = datetime.now(timezone.utc).replace(microsecond=0)
        source.write_text(
            "# L1 Assistant — Trusted Inbox & Sent Items\n"
            f"_Last updated: {now.strftime('%Y-%m-%d %H:%M')} UTC_\n\n"
            "## Sent Items\n\n"
            "---\n"
            f"**Test outbound**\nTo: Tom <tom@example.test> | {now.strftime('%Y-%m-%d %H:%M')}\n"
        )
        state_path = root / "monitoring-surface-state.json"
        state_path.write_text(
            '{"schema_version": 1, "surfaces": {'
            '"assistant_sent": {'
            '"surface": "assistant_sent", '
            '"source_file": "ASSISTANT_SENT.md", '
            '"last_successful_visible_update": "2026-07-29T16:53:00Z", '
            '"last_successful_check": "2026-07-29T16:54:03Z", '
            '"coverage_state": "clean", '
            '"last_result_shape": "new_visible_activity"'
            '}}}'
        )
        original_path = mod.SURFACE_STATE_PATH
        original_spec = mod.SURFACE_SPECS["assistant_sent"]["source_path"]
        try:
            mod.SURFACE_STATE_PATH = state_path
            mod.SURFACE_SPECS["assistant_sent"]["source_path"] = source
            mod._generic_continuity_report(
                surface_key="assistant_sent",
                source_path=source,
                title="Assistant Sent Continuity Report",
                threshold_hours=2,
                latest_visible_ts=now,
            )
            state = mod.load_surface_state()["surfaces"]["assistant_sent"]
            assert state["source_file"] == "ASSISTANT_INBOX.md"
            assert state["source_section"] == "## Sent Items"
            assert state["coverage_state"] == "clean"
            assert state["last_successful_visible_update"] != "2026-07-29T16:53:00Z"

            # A later feed refresh must not be treated as covered until the
            # continuity consumer has checked that refresh.
            state["last_successful_check"] = "2026-07-29T16:54:03Z"
            state_path.write_text(__import__("json").dumps({"schema_version": 1, "surfaces": {"assistant_sent": state}}))
            original_surfaces = mod.ALL_MONITORED_SURFACES
            mod.ALL_MONITORED_SURFACES = ("assistant_sent",)
            try:
                audit = mod.monitoring_surface_audit_report()
            finally:
                mod.ALL_MONITORED_SURFACES = original_surfaces
            assert "current coverage is not yet proven" in audit
        finally:
            mod.SURFACE_STATE_PATH = original_path
            mod.SURFACE_SPECS["assistant_sent"]["source_path"] = original_spec
    print("surface owner migration: OK")


if __name__ == "__main__":
    main()

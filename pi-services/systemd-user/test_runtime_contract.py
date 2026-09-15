#!/usr/bin/env python3
"""Static checks for the source-controlled runtime ownership contract.

These checks deliberately do not inspect or mutate a live systemd/crontab
installation.  They protect the distinction between the canonical router,
the retained legacy watcher units, and the source feed window.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "attached_assets" / "install-forked-openclaw.sh"
EXPENSE_SERVICE = ROOT / "pi-services" / "systemd-user" / "expense-intake-watcher.service"
EXPENSE_TIMER = ROOT / "pi-services" / "systemd-user" / "expense-intake-watcher.timer"
WHATSAPP_RECENT = ROOT / "attached_assets" / "scripts" / "whatsapp_recent.sh"
OPERATING = ROOT / "pi-services" / "expense-intake-watcher" / "OPERATING.md"
DEPLOYMENT = ROOT / "knowledge" / "pi-deployment.md"
REPLIT = ROOT / "replit.md"
WHATSAPP_DOC = ROOT / "knowledge" / "whatsapp.md"
REPAIR_DOC = ROOT / "docs" / "audits" / "openclaw-product" / "runtime-contract-repair.md"


class RuntimeContractStaticTests(unittest.TestCase):
    def test_retained_expense_units_are_explicit_legacy_opt_in(self) -> None:
        for unit in (EXPENSE_SERVICE, EXPENSE_TIMER):
            text = unit.read_text(encoding="utf-8").lower()
            self.assertIn("legacy", text, unit.name)
            self.assertIn("opt-in", text, unit.name)
            self.assertIn("not install", text, unit.name)
            self.assertIn("live", text, unit.name)

        service = EXPENSE_SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("/home/tomdean88/", service)
        self.assertIn("%h/openclaw/pi-services/expense-intake-watcher", service)

    def test_canonical_installer_never_installs_or_enables_legacy_timer(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("legacy expense watcher", installer.lower())
        self.assertRegex(
            installer,
            r"does not install(?: or)? enable",
            "installer must state that the legacy units are not managed by default",
        )
        self.assertNotRegex(
            installer,
            r"(?im)^\s*systemctl\s+--user\s+(?:enable|start|restart)\b[^\n]*expense-intake-watcher",
        )
        self.assertNotRegex(
            installer,
            r"(?im)^\s*(?:cp|install|ln(?:\s+-sf)?)\b[^\n]*expense-intake-watcher\.(?:service|timer)",
        )

    def test_expense_operating_doc_separates_policy_from_live_activation(self) -> None:
        operating = OPERATING.read_text(encoding="utf-8").lower()
        self.assertIn("source policy (fixed)", operating)
        self.assertIn("live activation is unknown", operating)
        self.assertIn("legacy opt-in fallback", operating)
        self.assertIn("installer does not install or enable", operating)

    def test_schedule_policy_keeps_pending_declarations_without_grandfathering_approval(self) -> None:
        deployment = DEPLOYMENT.read_text(encoding="utf-8")
        replit = REPLIT.read_text(encoding="utf-8")
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("06:xx and 07:xx", deployment)
        self.assertIn("pre-existing 06:55 health-check", deployment)
        self.assertRegex(
            deployment.lower(),
            r"schedule\s+inconsistency\s+remains\s+explicitly\s+pending",
        )
        self.assertIn("Do not add new", replit)
        self.assertIn("health 06:55", replit)
        self.assertIn("Monday AI briefing 06:00", replit)
        for text in (deployment, replit, installer):
            lowered = text.lower()
            self.assertNotRegex(lowered, r"approved\s+(?:installer\s+)?exceptions?")
            self.assertIn("pending", lowered)
        self.assertIn('HEALTH_CRON="55 6 * * *', installer)
        self.assertIn('AI_BRIEFING_CRON="0 6 * * 1', installer)
        self.assertIn("must not move", deployment.lower())

    def test_whatsapp_recent_feed_uses_approved_48_hour_semantic_window(self) -> None:
        script = WHATSAPP_RECENT.read_text(encoding="utf-8")
        self.assertRegex(script, r"(?m)^HOURS=48$")
        self.assertRegex(script, r"(?m)^\s*hours = 48$")
        self.assertNotRegex(script, r"(?m)^\s*(?:HOURS|hours)\s*=\s*72\b")
        self.assertIn("'window_hours': hours", script)
        self.assertIn("'coverage_complete': parse_errors == 0", script)
        self.assertIn("48-hour", WHATSAPP_DOC.read_text(encoding="utf-8"))

    def test_whatsapp_recent_runtime_distinguishes_missing_failed_and_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            raw = home / ".openclaw" / "credentials" / "whatsapp" / "watch-transcripts" / "whatsapp-watch-default.jsonl"
            workspace = home / ".openclaw" / "workspace"
            window = workspace / "memory" / "whatsapp-recent-window.json"
            raw.parent.mkdir(parents=True)
            window.parent.mkdir(parents=True)

            def run_generator(expected_returncode: int = 0) -> None:
                env = os.environ.copy()
                env["HOME"] = str(home)
                result = subprocess.run(
                    ["bash", str(WHATSAPP_RECENT)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(expected_returncode, result.returncode, result.stderr)

            # A missing source must replace any prior clean sidecar and must
            # not claim that zero messages were verified.
            window.write_text(
                json.dumps({
                    "source_status": "ok",
                    "coverage_status": "complete",
                    "coverage_complete": True,
                    "retained_message_count": 0,
                }),
                encoding="utf-8",
            )
            run_generator()
            missing = json.loads(window.read_text(encoding="utf-8"))
            self.assertEqual(missing["source_status"], "missing")
            self.assertEqual(missing["coverage_status"], "incomplete")
            self.assertFalse(missing["coverage_complete"])
            self.assertIsNone(missing["retained_message_count"])
            self.assertIsNone(missing["source_message_count"])
            self.assertIn("message absence is not verified", (workspace / "WHATSAPP_RECENT.md").read_text(encoding="utf-8"))

            # An existing, readable empty transcript is a real clean window:
            # zero is meaningful only in this case.
            raw.touch()
            run_generator()
            empty = json.loads(window.read_text(encoding="utf-8"))
            self.assertEqual(empty["source_status"], "ok")
            self.assertEqual(empty["coverage_status"], "complete")
            self.assertTrue(empty["coverage_complete"])
            self.assertEqual(empty["retained_message_count"], 0)
            self.assertEqual(empty["source_message_count"], 0)
            self.assertIn("(no messages in the last 48 hours)", (workspace / "WHATSAPP_RECENT.md").read_text(encoding="utf-8"))

            # A source read/decode failure must also replace the prior clean
            # status rather than leaving a stale sidecar in place.
            raw.write_bytes(b"\xff")
            run_generator(expected_returncode=1)
            failed = json.loads(window.read_text(encoding="utf-8"))
            self.assertEqual(failed["source_status"], "failed")
            self.assertEqual(failed["coverage_status"], "incomplete")
            self.assertFalse(failed["coverage_complete"])
            self.assertIsNone(failed["retained_message_count"])
            self.assertIsNone(failed["source_message_count"])

    def test_installer_google_recovery_matches_phone_callback_pollers(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("gmail_poll.py --auth", installer)
        self.assertIn("http://localhost:8766/", installer)
        self.assertIn("GCAL_POLLER=", installer)
        self.assertIn("$GCAL_POLLER --auth", installer)
        self.assertIn("http://localhost:8765/", installer)
        self.assertIn("do not delete an existing token", installer.lower())
        self.assertNotIn("opens browser for consent", installer.lower())
        self.assertNotIn("run that script on your desktop", installer.lower())
        self.assertNotIn("scp the token.json", installer.lower())

    def test_repair_record_separates_fixed_source_from_unknown_live_state(self) -> None:
        repair = REPAIR_DOC.read_text(encoding="utf-8")
        self.assertIn("Fixed source contract", repair)
        self.assertIn("Live state unknown", repair)
        self.assertIn("recover", repair.lower())
        self.assertIn("tests", repair.lower())


if __name__ == "__main__":
    unittest.main()
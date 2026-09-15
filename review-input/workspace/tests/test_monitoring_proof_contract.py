import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/inbound-monitoring.py"
spec = importlib.util.spec_from_file_location("inbound_monitoring", SCRIPT)
monitoring = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = monitoring
spec.loader.exec_module(monitoring)


class MonitoringProofContractTests(unittest.TestCase):
    def test_closed_without_evidence_becomes_coverage_incomplete(self):
        item = {"closure_state": "closed", "evidence_refs": [], "resolved_at": "2026-07-29T15:00:00Z"}
        result = monitoring._proof_safe_item(item)
        self.assertEqual(result["closure_state"], "coverage_incomplete")
        self.assertIsNone(result["resolved_at"])
        self.assertIn("no durable evidence", result["blocker"])

    def test_blocked_item_cannot_keep_resolved_at(self):
        item = {"closure_state": "blocked", "evidence_refs": [], "resolved_at": "2026-07-29T15:00:00Z"}
        result = monitoring._proof_safe_item(item)
        self.assertIsNone(result["resolved_at"])

    def test_source_later_than_seen_is_coverage_incomplete(self):
        item = {
            "closure_state": "closed",
            "evidence_refs": ["source.md"],
            "source_timestamp": "2026-07-29T16:00:00Z",
            "seen_at": "2026-07-29T15:00:00Z",
        }
        result = monitoring._proof_safe_item(item)
        self.assertEqual(result["closure_state"], "coverage_incomplete")
        self.assertIn("observation timing", result["blocker"])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from mirror_router import MirrorEvent

spec = importlib.util.spec_from_file_location("inbound_monitoring", SCRIPTS / "inbound-monitoring.py")
inbound_monitoring = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = inbound_monitoring
spec.loader.exec_module(inbound_monitoring)


class MirrorRoutingHandoffContractTests(unittest.TestCase):
    def test_handoff_json_contains_classified_task_system_candidate_not_raw_event(self):
        event = MirrorEvent(
            surface="microsoft_inbox", source_type="email", direction="inbound",
            sender="Tom Dean <tomdean1988@gmail.com>", subject_or_location="Testing reply service",
            body_preview="This email needs a reply", source_id="message-1", thread_key="thread-1",
            raw_evidence_ref="MICROSOFT_INBOX.md", coverage_state="clean",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "mirror-events.json"
            with patch.object(inbound_monitoring, "MIRROR_EVENTS_JSON_PATH", output), \
                 patch.object(inbound_monitoring, "build_canonical_mirror_events", return_value=[event]), \
                 patch.object(inbound_monitoring, "load_mirror_router_state", return_value={"seen": {}}), \
                 patch.object(inbound_monitoring, "load_crm_entity_candidates", return_value=[]):
                inbound_monitoring.mirror_routing_report(write_json=True)
            item = json.loads(output.read_text())["items"][0]

        self.assertEqual(item["draft_mode"], "task_system_context")
        self.assertEqual(item["management_relevance"], "needs_management")
        self.assertTrue(item["task_system_candidate"])
        self.assertEqual(item["raw_evidence_ref"], "MICROSOFT_INBOX.md")


if __name__ == "__main__":
    unittest.main()

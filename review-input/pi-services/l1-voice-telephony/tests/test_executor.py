from datetime import UTC, datetime
import unittest

from l1_voice_telephony.approval import (
    ActionRequest,
    ApprovalError,
    ApprovalService,
    AuthorityTier,
    CallerIdentity,
)
from l1_voice_telephony.executor import (
    ActionExecutionError,
    ApprovedActionExecutor,
)

NOW = datetime(2026, 8, 16, 18, 0, tzinfo=UTC)
KEY = b"k" * 32
TOM = CallerIdentity("tom", registered_tom_number=True, carrier_verified=True)
REQUEST = ActionRequest(
    action="mock_calendar_draft",
    target="Tom calendar",
    parameters={"title": "Voice test"},
    tier=AuthorityTier.MATERIAL_SENSITIVE,
)


class ApprovedActionExecutorTests(unittest.TestCase):
    def setUp(self):
        self.approvals = ApprovalService(KEY, now=lambda: NOW)
        self.events = []
        self.calls = []
        self.executor = ApprovedActionExecutor(
            approvals=self.approvals,
            handlers={"mock_calendar_draft": self.handler},
            now=lambda: NOW,
            audit_sink=self.events.append,
        )

    def handler(self, request):
        self.calls.append(request)
        return "mock-result"

    def grant(self):
        return self.approvals.mint(
            caller=TOM,
            request=REQUEST,
            spoken_confirmation=True,
        )

    def test_valid_grant_calls_only_the_allowlisted_handler_and_audits(self):
        result = self.executor.execute(
            correlation_id="call-001", caller=TOM, request=REQUEST, grant=self.grant()
        )
        self.assertEqual("mock-result", result)
        self.assertEqual([REQUEST], self.calls)
        self.assertEqual("succeeded", self.events[0].outcome)
        self.assertEqual("handler_completed", self.events[0].detail)
        self.assertNotIn("title", self.events[0].as_safe_dict())

    def test_invalid_grant_cannot_reach_handler_or_emit_success(self):
        grant = self.grant()
        changed = ActionRequest(
            action=REQUEST.action,
            target="Lauren calendar",
            parameters=REQUEST.parameters,
            tier=REQUEST.tier,
        )
        with self.assertRaises(ApprovalError):
            self.executor.execute(
                correlation_id="call-002", caller=TOM, request=changed, grant=grant
            )
        self.assertEqual([], self.calls)
        self.assertEqual([], self.events)

    def test_missing_handler_consumes_the_grant_then_audits_safe_rejection(self):
        unknown = ActionRequest(
            action="unregistered_action",
            target="somewhere",
            parameters={},
            tier=AuthorityTier.INFORMATION,
        )
        grant = self.approvals.mint(caller=TOM, request=unknown, spoken_confirmation=True)
        with self.assertRaisesRegex(ActionExecutionError, "no allowlisted handler"):
            self.executor.execute(
                correlation_id="call-003", caller=TOM, request=unknown, grant=grant
            )
        self.assertEqual([], self.calls)
        self.assertEqual("rejected", self.events[0].outcome)
        self.assertEqual("no_allowlisted_handler", self.events[0].detail)


if __name__ == "__main__":
    unittest.main()

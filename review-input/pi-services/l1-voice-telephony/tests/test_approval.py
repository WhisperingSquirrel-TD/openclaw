from dataclasses import replace
from datetime import UTC, datetime, timedelta
import unittest

from l1_voice_telephony.approval import (
    ActionRequest,
    ApprovalError,
    ApprovalService,
    AuthorityTier,
    CallerIdentity,
)

NOW = datetime(2026, 8, 16, 18, 0, tzinfo=UTC)
KEY = b"k" * 32
TOM = CallerIdentity("tom", registered_tom_number=True, carrier_verified=True)
OTHER = CallerIdentity("other", registered_tom_number=False, carrier_verified=True)
REQUEST = ActionRequest(
    action="create_calendar_event",
    target="Tom calendar",
    parameters={"title": "Call Sam", "start": "2026-08-17T09:00:00+01:00"},
    tier=AuthorityTier.MATERIAL_SENSITIVE,
)


class ApprovalServiceTests(unittest.TestCase):
    def service(self, now=NOW):
        return ApprovalService(KEY, now=lambda: now)

    def test_fresh_confirmed_tom_request_is_consumable_once(self):
        approvals = self.service()
        grant = approvals.mint(caller=TOM, request=REQUEST, spoken_confirmation=True)

        approvals.consume(grant=grant, caller=TOM, request=REQUEST)

        with self.assertRaisesRegex(ApprovalError, "already been consumed"):
            approvals.consume(grant=grant, caller=TOM, request=REQUEST)

    def test_unregistered_caller_cannot_mint_authority(self):
        with self.assertRaisesRegex(ApprovalError, "authenticated Tom"):
            self.service().mint(caller=OTHER, request=REQUEST, spoken_confirmation=True)

    def test_confirmation_is_required_even_for_registered_tom_number(self):
        with self.assertRaisesRegex(ApprovalError, "spoken confirmation"):
            self.service().mint(caller=TOM, request=REQUEST, spoken_confirmation=False)

    def test_prohibited_action_is_rejected_before_any_grant_exists(self):
        forbidden = ActionRequest(
            action="pay_deposit",
            target="restaurant",
            parameters={"amount_pence": 1000},
            tier=AuthorityTier.PROHIBITED,
        )
        with self.assertRaisesRegex(ApprovalError, "prohibited"):
            self.service().mint(caller=TOM, request=forbidden, spoken_confirmation=True)

    def test_changed_destination_or_parameters_invalidates_the_grant(self):
        approvals = self.service()
        grant = approvals.mint(caller=TOM, request=REQUEST, spoken_confirmation=True)
        changed = ActionRequest(
            action=REQUEST.action,
            target="Lauren calendar",
            parameters=REQUEST.parameters,
            tier=REQUEST.tier,
        )
        with self.assertRaisesRegex(ApprovalError, "does not match"):
            approvals.consume(grant=grant, caller=TOM, request=changed)

    def test_expired_grant_is_rejected(self):
        approvals = self.service()
        grant = approvals.mint(
            caller=TOM,
            request=REQUEST,
            spoken_confirmation=True,
            lifetime=timedelta(seconds=30),
        )
        later = self.service(now=NOW + timedelta(seconds=31))
        with self.assertRaisesRegex(ApprovalError, "expired"):
            later.consume(grant=grant, caller=TOM, request=REQUEST)

    def test_tampered_token_is_rejected(self):
        approvals = self.service()
        grant = approvals.mint(caller=TOM, request=REQUEST, spoken_confirmation=True)
        forged = replace(grant, token="not-a-valid-signature")
        with self.assertRaisesRegex(ApprovalError, "signature"):
            approvals.consume(grant=forged, caller=TOM, request=REQUEST)


if __name__ == "__main__":
    unittest.main()

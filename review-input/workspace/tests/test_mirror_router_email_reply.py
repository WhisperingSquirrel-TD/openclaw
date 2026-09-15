import unittest

from scripts.mirror_router import MirrorEvent, classify_mirror_event


class MirrorRouterEmailReplyTests(unittest.TestCase):
    def test_trusted_reply_worthy_email_prefers_task_system_context_when_crm_heavy(self):
        event = MirrorEvent(
            surface="microsoft_inbox",
            source_type="email",
            direction="inbound",
            sender="Stuart Hobin <stuart.hobin@croydemedical.co.uk>",
            subject_or_location="Re: Options summary",
            body_preview="Can you clarify the confidence level and what option B means for us?",
            thread_key="AAQk-croyde-thread",
            source_id="msg-1",
            trust_class="trusted",
        )
        result = classify_mirror_event(event, entity_candidates=[("Croyde Medical", ["Stuart Hobin", "Croyde Medical"])])
        self.assertEqual(result["reply_likelihood"], "likely")
        self.assertEqual(result["draft_mode"], "task_system_context")
        self.assertTrue(result["task_system_candidate"])
        self.assertFalse(result["promotion_candidate"])
        self.assertEqual(result["closure_state"], "classified")

    def test_external_reply_worthy_email_requires_gate(self):
        event = MirrorEvent(
            surface="microsoft_external",
            source_type="email",
            direction="inbound",
            sender="Grant Fagan <grant@grantfagan.com>",
            subject_or_location="Re: Call follow-up",
            body_preview="Can you send a short summary I can forward on please?",
            thread_key="AAQk-grant-thread",
            source_id="msg-2",
            trust_class="external",
        )
        result = classify_mirror_event(event, entity_candidates=[("Grant Fagan", ["Grant Fagan", "grant@grantfagan.com"])])
        self.assertEqual(result["reply_likelihood"], "likely")
        self.assertEqual(result["draft_mode"], "gated_full_read")
        self.assertEqual(result["readability_strength"], "external_withheld")
        self.assertTrue(result["promotion_candidate"])
        self.assertEqual(result["closure_state"], "blocked")

    def test_non_reply_external_receipt_is_not_promotion_candidate(self):
        event = MirrorEvent(
            surface="microsoft_external",
            source_type="email",
            direction="inbound",
            sender="Replit <invoice@example.com>",
            subject_or_location="Your receipt from Replit #2453-4920",
            body_preview="Your receipt is attached.",
            thread_key="receipt-thread",
            source_id="msg-3",
            trust_class="external",
        )
        result = classify_mirror_event(event, entity_candidates=[])
        self.assertEqual(result["reply_likelihood"], "none")
        self.assertFalse(result["promotion_candidate"])
        self.assertEqual(result["draft_mode"], "none")


if __name__ == "__main__":
    unittest.main()

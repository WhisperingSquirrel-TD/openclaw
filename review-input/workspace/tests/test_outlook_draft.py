import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

INTEGRATION_DIR = Path("/home/tomdean88/.openclaw/integrations/microsoft-l1")
sys.path.insert(0, str(INTEGRATION_DIR))
import draft  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status_code=201):
        self._payload = payload
        self.status_code = status_code
        self.text = ""
        self.content = b"payload"

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class OutlookDraftTests(unittest.TestCase):
    def test_new_draft_uses_messages_endpoint_and_never_send(self):
        calls = []

        def post(url, **kwargs):
            calls.append(("POST", url, kwargs))
            return FakeResponse({"id": "draft-123", "subject": "Test", "webLink": "https://outlook.example/draft-123"})

        fake_requests = types.SimpleNamespace(post=post, patch=lambda *a, **k: self.fail("new draft should not PATCH"))
        with patch.dict(sys.modules, {"requests": fake_requests}):
            result = draft.create_draft(
                "token", ["tom@example.test"], "Test", "Body", body_content_type="text", bcc_recipients=[], attachments=[]
            )

        self.assertEqual(result["id"], "draft-123")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "https://graph.microsoft.com/v1.0/me/messages")
        self.assertNotIn("send", calls[0][1])

    def test_reply_draft_creates_and_updates_but_never_sends(self):
        calls = []

        def post(url, **kwargs):
            calls.append(("POST", url, kwargs))
            return FakeResponse({"id": "reply-draft-456", "subject": "Re: Existing"})

        def patch_request(url, **kwargs):
            calls.append(("PATCH", url, kwargs))
            return FakeResponse({"id": "reply-draft-456", "subject": "Re: Existing"}, status_code=200)

        fake_requests = types.SimpleNamespace(post=post, patch=patch_request)
        with patch.dict(sys.modules, {"requests": fake_requests}):
            result = draft.create_draft(
                "token", ["tom@example.test"], "Re: Existing", "Body", body_content_type="text", bcc_recipients=[], attachments=[],
                reply_to_message_id="source-message-id",
            )

        self.assertEqual(result["id"], "reply-draft-456")
        urls = [call[1] for call in calls]
        self.assertEqual(urls[0], "https://graph.microsoft.com/v1.0/me/messages/source-message-id/createReply")
        self.assertEqual(urls[1], "https://graph.microsoft.com/v1.0/me/messages/reply-draft-456")
        self.assertTrue(all("/send" not in url and "sendMail" not in url for url in urls))


if __name__ == "__main__":
    unittest.main()

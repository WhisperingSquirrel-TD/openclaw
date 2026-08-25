import hashlib
import hmac
import importlib.util
import json
import os
import base64
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("send.py")
SPEC = importlib.util.spec_from_file_location("microsoft_send", MODULE_PATH)
assert SPEC and SPEC.loader
send = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(send)


class TaskDispatchPermitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / "used.json"
        self.lock = root / "used.lock"
        self.audit = root / "audit.log"
        self.key = "x" * 32
        self.email_digest = "a" * 64
        self.now = 1_700_000_000
        self.patches = [
            patch.object(send, "TASK_DISPATCH_STATE_PATH", self.state),
            patch.object(send, "TASK_DISPATCH_LOCK_PATH", self.lock),
            patch.object(send, "TASK_DISPATCH_AUDIT_PATH", self.audit),
            patch.object(send.time, "time", return_value=self.now),
            patch.dict(os.environ, {send.TASK_DISPATCH_KEY_ENV: self.key}),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def write_permit(self, **overrides):
        permit = {
            "version": 1,
            "audience": send.TASK_DISPATCH_AUDIENCE,
            "task_id": "task-42",
            "draft_id": "draft-42",
            "jti": "permit-42",
            "expires_at": self.now + 60,
            "email_digest": self.email_digest,
        }
        permit.update(overrides)
        permit["signature"] = hmac.new(
            self.key.encode("utf-8"),
            send._canonical_json(permit),
            hashlib.sha256,
        ).hexdigest()
        path = Path(self.tmp.name) / "permit.json"
        path.write_text(json.dumps(permit), encoding="utf-8")
        return path

    def test_valid_permit_is_consumed_once(self):
        permit = self.write_permit()
        result = send.verify_and_consume_task_dispatch_permit(str(permit), self.email_digest)

        self.assertEqual(result, {"task_id": "task-42", "permit_id": "permit-42"})
        with self.assertRaisesRegex(ValueError, "already used"):
            send.verify_and_consume_task_dispatch_permit(str(permit), self.email_digest)

    def test_rejects_modified_email_expired_and_long_lived_permits(self):
        permit = self.write_permit()
        with self.assertRaisesRegex(ValueError, "does not match"):
            send.verify_and_consume_task_dispatch_permit(str(permit), "b" * 64)

        expired = self.write_permit(jti="expired", expires_at=self.now - 1)
        with self.assertRaisesRegex(ValueError, "expired"):
            send.verify_and_consume_task_dispatch_permit(str(expired), self.email_digest)

        long_lived = self.write_permit(
            jti="long-lived",
            expires_at=self.now + send.TASK_DISPATCH_MAX_TTL_SECONDS + 1,
        )
        with self.assertRaisesRegex(ValueError, "exceeds"):
            send.verify_and_consume_task_dispatch_permit(str(long_lived), self.email_digest)

    def test_rejects_forged_signature(self):
        permit = self.write_permit()
        data = json.loads(permit.read_text(encoding="utf-8"))
        data["email_digest"] = "b" * 64
        permit.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "signature is invalid"):
            send.verify_and_consume_task_dispatch_permit(str(permit), "b" * 64)

    def test_attachment_snapshot_cannot_change_after_permit_binding(self):
        attachment = Path(self.tmp.name) / "proposal.txt"
        attachment.write_bytes(b"owner-approved")
        graph_attachments, fingerprints = send._build_attachment_snapshot([str(attachment)])
        before = send.email_fingerprint(
            recipients=["owner@example.com"],
            cc_recipients=[],
            bcc_recipients=[],
            from_name="Assistant",
            subject="Proposal",
            body="Please review",
            body_content_type="text",
            reply_to_message_id=None,
            reply_all=False,
            attachment_fingerprints=fingerprints,
        )

        attachment.write_bytes(b"changed after approval")
        after = send.email_fingerprint(
            recipients=["owner@example.com"],
            cc_recipients=[],
            bcc_recipients=[],
            from_name="Assistant",
            subject="Proposal",
            body="Please review",
            body_content_type="text",
            reply_to_message_id=None,
            reply_all=False,
            attachment_fingerprints=fingerprints,
        )

        self.assertEqual(before, after)
        self.assertEqual(
            base64.b64decode(graph_attachments[0]["contentBytes"]),
            b"owner-approved",
        )

    def test_email_fingerprint_binds_cc_recipients(self):
        common = {
            "recipients": ["owner@example.com"],
            "bcc_recipients": [],
            "from_name": "Assistant",
            "subject": "Proposal",
            "body": "Please review",
            "body_content_type": "text",
            "reply_to_message_id": "message-1",
            "reply_all": True,
            "attachment_fingerprints": [],
        }
        no_cc = send.email_fingerprint(cc_recipients=[], **common)
        with_cc = send.email_fingerprint(cc_recipients=["observer@example.com"], **common)
        self.assertNotEqual(no_cc, with_cc)

    def test_reply_clears_inherited_cc_and_bcc_when_not_signed_off(self):
        graph_patch = {}
        post_responses = iter([
            SimpleNamespace(ok=True, json=lambda: {"id": "reply-draft"}),
            SimpleNamespace(status_code=202, text=""),
        ])

        def post(*_args, **_kwargs):
            return next(post_responses)

        def patch_request(*_args, **kwargs):
            graph_patch.update(kwargs["json"])
            return SimpleNamespace(ok=True, status_code=200, text="")

        with patch.object(send.requests, "post", side_effect=post), patch.object(
            send.requests, "patch", side_effect=patch_request
        ):
            send.send_email(
                "test-token",
                recipients=["owner@example.com"],
                from_name="Assistant",
                subject="Proposal",
                body="Please review",
                reply_to_message_id="original-message",
                reply_all=True,
                cc_recipients=[],
                bcc_recipients=[],
            )

        self.assertEqual(graph_patch["ccRecipients"], [])
        self.assertEqual(graph_patch["bccRecipients"], [])
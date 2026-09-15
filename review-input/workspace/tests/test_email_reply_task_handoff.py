import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path('/home/tomdean88/.openclaw/workspace/scripts/email-reply-task-handoff.py')
spec = importlib.util.spec_from_file_location('email_reply_task_handoff', SCRIPT)
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class EmailReplyTaskHandoffTests(unittest.TestCase):
    def test_reply_worthy_candidates_are_admitted_without_safe_sender_suppression(self):
        items = handoff.event_candidates([
            {'surface': 'microsoft_inbox', 'direction': 'inbound', 'reply_decision': 'reply_needed', 'draft_mode': 'task_system_context', 'stable_item_key': 'trusted-1', 'source_id': 'trusted-message-1', 'thread_key': 'trusted-thread-1'},
            {'surface': 'microsoft_external', 'direction': 'inbound', 'reply_decision': 'reply_needed', 'draft_mode': 'gated_full_read', 'stable_item_key': 'external-1', 'source_id': 'external-message-1', 'thread_key': 'external-thread-1'},
            {'surface': 'microsoft_inbox', 'direction': 'inbound', 'reply_decision': 'no_reply_needed', 'draft_mode': 'task_system_context', 'stable_item_key': 'noise-1', 'source_id': 'noise-message-1', 'thread_key': 'noise-thread-1'},
        ])
        self.assertEqual([item['stable_item_key'] for item in items], ['trusted-1', 'external-1'])

    def test_gateway_task_tree_verifies_matching_canonical_task_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = handoff.canonical_event_id(surface='microsoft_inbox', provider_event_id='message', provider_conversation_id='thread')
            (root / 'intake-events.jsonl').write_text(json.dumps({'event_id': canonical}) + '\n')
            record = {'stable_item_key': 'microsoft_inbox:email:thread:message', 'task_id': 'task-1'}
            self.assertTrue(handoff.sync_task_destination_receipt(record, ledger_root=root))
            receipt = json.loads((root / 'intake-route-receipts.jsonl').read_text())
            self.assertEqual(receipt['state'], 'verified')
            self.assertEqual(receipt['destination_ref'], 'task:task-1')

    def test_handoff_uses_one_gateway_owned_idempotent_admission(self):
        calls = []
        def fake_api(method, path, token, payload=None, allow_error=False):
            calls.append((method, path, payload, allow_error))
            return {'ok': True, 'task': {'id': 'task-1'}, 'subtasks': [{'id': 'sub-prep'}, {'id': 'sub-output'}, {'id': 'sub-review'}], 'operator_signal': {'id': 'signal-1'}, 'status': 'ready'}
        event = {'stable_item_key': 'microsoft_inbox:email:thread:message', 'surface': 'microsoft_inbox', 'sender': 'Stuart Hobin <stuart@example.com>', 'subject_or_location': 'Re: Options summary', 'thread_key': 'thread', 'source_id': 'message'}
        original = handoff.api; handoff.api = fake_api
        try:
            task_id, prep_id, review_id, result = handoff.create_reply_prep(event, 'token', 'objective-1')
        finally:
            handoff.api = original
        self.assertEqual((task_id, prep_id, review_id), ('task-1', 'sub-prep', 'sub-review'))
        self.assertEqual([call[1] for call in calls], ['/task-intake/brief'])
        payload = calls[0][2]
        self.assertEqual(payload['idempotency_key'], 'email-reply-admission:microsoft_inbox:email:thread:message')
        self.assertEqual(payload['reply_mode'], 'reply_inbound')
        self.assertEqual(payload['source_refs'], ['microsoft_inbox:email:thread:message'])
        self.assertEqual(result['operator_signal']['id'], 'signal-1')


if __name__ == '__main__':
    unittest.main()

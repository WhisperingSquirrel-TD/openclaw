import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'crm-capture-handoff.py'
spec = importlib.util.spec_from_file_location('crm_capture_handoff', SCRIPT)
M = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = M
spec.loader.exec_module(M)

CRM = '''# Stackstone CRM
## Opportunities
| Company | Primary Contact | Stage | Last Touch | Next Step | Campaign Eligible | SharePoint Path |
|---|---|---|---|---|---|---|
| Other | A | Opportunity | 01/01/2026 | Watch | No | /Opportunities/Other/Other - Current.md |

## Accounts
| Company | Primary Contact | Stage | Last Touch | Next Step | Campaign Eligible | SharePoint Path |
|---|---|---|---|---|---|---|
| Croyde Medical | Stuart Hobin | Client | 13/08/2026 | Existing control | No | /Accounts/Croyde Medical/Croyde Medical - Current.md |
'''


def event(key='wa-commit-1'):
    return {'event_id': f'whatsapp_recent:direct:Stuart Hobin:{key}', 'state': 'queued', 'entity': 'Croyde Medical',
            'entity_mapping': {'status': 'mapped', 'entity': 'Croyde Medical', 'entity_type': 'Account', 'candidates': ['Croyde Medical']},
            'source_timestamp': '2026-08-14T20:30:00Z', 'source_line_ref': 'WHATSAPP_RECENT.md:L41-L42',
            'last_touch_date': '2026-08-14', 'next_action_control': "Create Stuart's agreed project brief.",
            'subject_or_location': 'Stuart Hobin'}


class ControlledWriterTests(unittest.TestCase):
    def test_croyde_stuart_account_queues_two_ops_and_local_control_without_claiming_confirmation(self):
        state, crm, queue, actions = M.controlled_write({'items': [event()]}, CRM, [], [])
        item = state['items'][0]
        self.assertEqual(item['state'], 'sharepoint_queued')
        self.assertEqual(len(queue), 2)
        self.assertEqual({q['operation'] for q in queue}, {'create', 'append'})
        self.assertIn('/Accounts/Croyde Medical/2026-08-14 - Outbound Commitment - Stuart Hobin.md', queue[0]['path'])
        self.assertEqual(queue[1]['path'], '/Accounts/Croyde Medical/Croyde Medical - Current.md')
        self.assertIn('2026-08-14', crm)
        self.assertIn('confirmation pending', crm)
        self.assertEqual(actions[0]['outcome'], 'queued')
        self.assertEqual(item['writer']['proof_requirements']['all_queue_ids_must_succeed'], True)

    def test_only_both_successful_queue_results_confirm(self):
        pending, crm, queue, _ = M.controlled_write({'items': [event()]}, CRM, [], [])
        ids = pending['items'][0]['writer']['queue_ids']
        state, unchanged_crm, unchanged_queue, actions = M.controlled_write(
            pending, crm, queue, [{'id': ids[0], 'success': True, 'processed_at': 'x'}, {'id': ids[1], 'success': True, 'processed_at': 'y'}])
        self.assertEqual(state['items'][0]['state'], 'confirmed')
        self.assertEqual(actions[0]['outcome'], 'confirmed')
        self.assertEqual(unchanged_crm, crm)
        self.assertEqual(unchanged_queue, queue)

    def test_missing_or_failed_proof_never_claims_confirmation(self):
        pending, crm, queue, _ = M.controlled_write({'items': [event()]}, CRM, [], [])
        ids = pending['items'][0]['writer']['queue_ids']
        waiting, _, _, _ = M.controlled_write(pending, crm, queue, [{'id': ids[0], 'success': True}])
        self.assertEqual(waiting['items'][0]['state'], 'sharepoint_queued')
        blocked, _, _, _ = M.controlled_write(pending, crm, queue, [{'id': ids[0], 'success': True}, {'id': ids[1], 'success': False}])
        self.assertEqual(blocked['items'][0]['state'], 'blocked')

    def test_router_admission_to_controlled_proof_closes_one_canonical_crm_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_event = {
                'stable_item_key': 'whatsapp_recent:direct:Stuart Hobin:wa-e2e-1',
                'owning_system': 'crm', 'management_relevance': 'needs_management',
                'candidate_entities': ['Croyde Medical'], 'surface': 'whatsapp_recent', 'direction': 'inbound',
                'source_timestamp': '2026-08-14T20:30:00Z', 'source_line_ref': 'WHATSAPP_RECENT.md:L41-L42',
                'subject_or_location': 'Stuart Hobin', 'required_next_action': "Create Stuart's agreed project brief.",
                'outbound_commitment_control': {'last_touch_date': '2026-08-14', 'next_action': "Create Stuart's agreed project brief."},
                'entity_mapping': {'status': 'mapped', 'entity': 'Croyde Medical', 'entity_type': 'Account'},
            }
            admitted = M.capture({'items': [source_event]}, {'items': []})
            pending, crm, queue, _ = M.controlled_write(admitted, CRM, [], [])
            ids = pending['items'][0]['writer']['queue_ids']
            confirmed, _, _, _ = M.controlled_write(pending, crm, queue, [{'id': ids[0], 'success': True}, {'id': ids[1], 'success': True}])
            canonical = M.canonical_event_id(surface='whatsapp_recent', provider_event_id='wa-e2e-1', provider_conversation_id='Stuart Hobin')
            (root / 'intake-events.jsonl').write_text(json.dumps({'event_id': canonical}) + '\n')
            self.assertEqual(M.sync_canonical_receipts(confirmed, ledger_root=root), 1)
            receipt = json.loads((root / 'intake-route-receipts.jsonl').read_text())
            self.assertEqual(receipt['state'], 'verified')
            self.assertEqual(receipt['route'], 'crm')

    def test_confirmed_controlled_writer_proof_verifies_existing_canonical_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = M.canonical_event_id(surface='whatsapp_recent', provider_event_id='wa-commit-1', provider_conversation_id='Stuart Hobin')
            (root / 'intake-events.jsonl').write_text(json.dumps({'event_id': canonical}) + '\n')
            item = event()
            item['state'] = 'confirmed'
            item['reconciliation_proof'] = {'artifact': {'id': 'artifact-proof'}, 'current': {'id': 'current-proof'}}
            self.assertEqual(M.sync_canonical_receipts({'items': [item]}, ledger_root=root), 1)
            receipt = json.loads((root / 'intake-route-receipts.jsonl').read_text())
            self.assertEqual(receipt['state'], 'verified')
            self.assertEqual(receipt['event_id'], canonical)
            self.assertIn('artifact-proof', receipt['destination_ref'])

    def test_missing_source_reference_is_blocked_and_writes_nothing(self):
        incomplete = event('no-source')
        incomplete.pop('source_line_ref')
        state, crm, queue, actions = M.controlled_write({'items': [incomplete]}, CRM, [], [])
        self.assertEqual(state['items'][0]['state'], 'blocked')
        self.assertEqual(queue, [])
        self.assertEqual(crm, CRM)
        self.assertIn('source evidence/ref', actions[0]['reason'])

    def test_ambiguous_event_is_blocked_and_writes_nothing(self):
        ambiguous = event('ambiguous')
        ambiguous['entity'] = None
        ambiguous['entity_mapping'] = {'status': 'ambiguous', 'entity_type': 'Account', 'candidates': ['Croyde Medical', 'Other']}
        state, crm, queue, actions = M.controlled_write({'items': [ambiguous]}, CRM, [], [])
        self.assertEqual(state['items'][0]['state'], 'blocked')
        self.assertEqual(queue, [])
        self.assertEqual(crm, CRM)
        self.assertEqual(actions[0]['outcome'], 'blocked')


if __name__ == '__main__':
    unittest.main()

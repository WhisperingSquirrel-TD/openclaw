from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seer_finance.ledger.expense_capture_adapter import capture_candidate
from seer_finance.ledger.expense_repository import ExpenseRepository


class ExpenseCaptureAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.database = self.root / 'ledger.sqlite3'
        self.replay = self.root / 'replay.json'

    def tearDown(self):
        self.tempdir.cleanup()

    def test_captures_source_linked_partial_facts_idempotently(self):
        first = capture_candidate(source_surface='telegram', source_ref='telegram:42',
                                  facts={'supplier': 'Unknown', 'evidence_ref': 'telegram:42', 'direction': 'expense'},
                                  database=self.database, replay_path=self.replay)
        replay = capture_candidate(source_surface='telegram', source_ref='telegram:42',
                                   facts={'supplier': 'Unknown', 'evidence_ref': 'telegram:42'},
                                   database=self.database, replay_path=self.replay)
        self.assertEqual('captured', first.outcome)
        self.assertEqual('captured', replay.outcome)
        self.assertEqual(first.expense_id, replay.expense_id)
        repo = ExpenseRepository(self.database)
        try:
            self.assertEqual('needs_review', repo.get(first.expense_id).status.value)
        finally:
            repo.close()
        self.assertFalse(self.replay.exists())

    def test_failure_preserves_one_replay_item_without_losing_facts(self):
        bad_database = self.root / 'not-a-db-parent' / 'ledger.sqlite3'
        bad_database.parent.write_text('not a directory', encoding='utf-8')
        result = capture_candidate(source_surface='email', source_ref='mail:1',
                                   facts={'source_timestamp': '2026-08-10T12:00:00Z'},
                                   database=bad_database, replay_path=self.replay)
        self.assertEqual('replayed', result.outcome)
        saved = json.loads(self.replay.read_text(encoding='utf-8'))
        self.assertEqual('mail:1', saved['items'][0]['source_ref'])
        self.assertEqual('2026-08-10T12:00:00Z', saved['items'][0]['facts']['source_timestamp'])
        self.assertIn('sqlite_capture_failed', saved['items'][0]['blocker'])

    def test_explicit_income_does_not_create_an_expense_or_replay_record(self):
        result = capture_candidate(source_surface='tide', source_ref='tide:income:1',
                                   facts={'direction': 'income', 'amount_pence': 4000},
                                   database=self.database, replay_path=self.replay)
        self.assertEqual('accounting_only', result.outcome)
        self.assertEqual('explicit_non_expense_direction:income', result.blocker)
        self.assertFalse(self.database.exists())
        self.assertFalse(self.replay.exists())

    def test_source_reference_validation_fails_before_any_write(self):
        with self.assertRaises(ValueError):
            capture_candidate(source_surface='email', source_ref='', database=self.database, replay_path=self.replay)
        self.assertFalse(self.database.exists())
        self.assertFalse(self.replay.exists())


if __name__ == '__main__':
    unittest.main()

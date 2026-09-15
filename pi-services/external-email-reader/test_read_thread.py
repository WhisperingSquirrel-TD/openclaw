#!/usr/bin/env python3
import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name('read_thread.py')
spec = importlib.util.spec_from_file_location('external_email_reader', MODULE_PATH)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class NormaliseMessageTests(unittest.TestCase):
    def test_normalises_html_and_classifies_draft(self):
        message = {
            'id': 'message-1',
            'conversationId': 'conversation-1',
            'from': {'emailAddress': {'address': 'outside@example.test'}},
            'toRecipients': [{'emailAddress': {'address': 'tom@example.test'}}],
            'body': {'contentType': 'html', 'content': '<p>Current</p><div id="x_divRplyFwdMsg">quoted</div>'},
            'isDraft': True,
        }

        result = reader.normalise_message(message)

        self.assertEqual(result['raw_body'], message['body']['content'])
        self.assertEqual(result['authored_content'], 'Current')
        self.assertEqual(result['body'], 'Current')
        self.assertEqual(result['to'], ['tom@example.test'])
        self.assertEqual(result['status'], 'draft')
        self.assertTrue(result['is_draft'])

    def test_classifies_outbound_message(self):
        result = reader.normalise_message({
            'id': 'message-2',
            'from': {'emailAddress': {'address': 'Tom@StackstoneConsulting.co.uk'}},
            'body': {'content': 'Sent'},
        })

        self.assertEqual(result['status'], 'sent')
        self.assertEqual(result['sender'], 'tom@stackstoneconsulting.co.uk')


class ExactThreadTests(unittest.TestCase):
    def test_escapes_conversation_filter_and_returns_bounded_thread(self):
        anchor = {
            'id': 'anchor',
            'conversationId': "thread'quoted",
            'subject': 'Subject',
            'from': {'emailAddress': {'address': 'outside@example.test'}},
            'receivedDateTime': '2026-09-01T08:00:00Z',
            'body': {'content': '<p>Current</p>'},
        }
        calls = []

        def fake_graph_get(url, access, params=None):
            calls.append((url, access, params))
            if params is None:
                return anchor
            return {'value': [anchor]}

        with patch.object(reader, 'token', return_value='not-a-real-token'), patch.object(
            reader, 'graph_get', side_effect=fake_graph_get
        ), patch.object(sys, 'argv', ['read_thread.py', 'anchor']), contextlib.redirect_stdout(
            io.StringIO()
        ) as output:
            self.assertEqual(reader.main(), 0)

        self.assertEqual(
            calls[1][2],
            {'$filter': "conversationId eq 'thread''quoted'", '$top': '21'},
        )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload['message_count'], 1)
        self.assertEqual(payload['messages'][0]['authored_content'], 'Current')


if __name__ == '__main__':
    unittest.main()
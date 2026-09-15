#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name('read_thread.py')
spec = importlib.util.spec_from_file_location('trusted_email_reader', MODULE_PATH)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class AuthoredBodyTests(unittest.TestCase):
    def test_strips_outlook_x_prefixed_reply_separator_and_html(self):
        content = (
            '<html><body><div>Current update<br>with detail</div>'
            '<hr><div id="x_divRplyFwdMsg"><b>From:</b> Vendor</div></body></html>'
        )
        self.assertEqual(reader.authored_body(content), 'Current update\nwith detail')

    def test_strips_mobile_separator_with_attribute_order_variation(self):
        content = '<div>Latest</div><div class="x" id="x_ms-outlook-mobile-body-separator-line">old thread</div>'
        self.assertEqual(reader.authored_body(content), 'Latest')


class NormaliseMessageTests(unittest.TestCase):
    def test_keeps_raw_body_and_normalised_metadata(self):
        message = {
            'id': 'message-1',
            'conversationId': 'conversation-1',
            'subject': 'Status',
            'from': {'emailAddress': {'address': 'TOM@STACKSTONECONSULTING.CO.UK'}},
            'toRecipients': [{'emailAddress': {'address': 'Contact@Example.test'}}],
            'ccRecipients': [{'emailAddress': {'address': 'Copy@Example.test'}}],
            'receivedDateTime': '2026-09-01T08:00:00Z',
            'sentDateTime': '2026-09-01T07:59:00Z',
            'body': {'contentType': 'html', 'content': '<div>Hello &amp; welcome<br>today</div><hr>quoted'},
        }

        result = reader.normalise_message(message)

        self.assertEqual(result['raw_body'], message['body']['content'])
        self.assertEqual(result['authored_content'], 'Hello & welcome\ntoday')
        self.assertEqual(result['body'], result['authored_content'])
        self.assertEqual(result['to'], ['contact@example.test'])
        self.assertEqual(result['cc'], ['copy@example.test'])
        self.assertEqual(result['status'], 'sent')
        self.assertFalse(result['is_draft'])


if __name__ == '__main__':
    unittest.main()

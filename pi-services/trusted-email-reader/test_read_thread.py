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


if __name__ == '__main__':
    unittest.main()

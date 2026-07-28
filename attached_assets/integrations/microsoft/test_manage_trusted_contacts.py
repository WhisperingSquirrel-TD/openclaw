#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("manage_trusted_contacts.py")
spec = importlib.util.spec_from_file_location("manage_trusted_contacts", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TrustedContactsToolTests(unittest.TestCase):
    def test_email_normalisation(self):
        self.assertEqual(mod.normalise_email(" Grant@GrantFagan.com "), "grant@grantfagan.com")
        with self.assertRaises(SystemExit):
            mod.normalise_email("not-an-email")

    def test_list_reads_only_canonical_data_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "known-contacts.txt"
            p.write_text("# comment\nOne@example.com\n\n")
            old = mod.CONTACTS_FILE
            try:
                mod.CONTACTS_FILE = p
                _, entries = mod.read_entries()
                self.assertEqual(entries, ["one@example.com"])
            finally:
                mod.CONTACTS_FILE = old

    def test_mutation_refuses_non_root(self):
        if mod.os.geteuid() == 0:
            self.skipTest("non-root mutation guard cannot be tested under root")
        with self.assertRaises(SystemExit):
            mod.mutate("add", "example@example.com")


if __name__ == "__main__":
    unittest.main()

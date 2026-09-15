#!/usr/bin/env python3
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path


HERE = Path(__file__).parent


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


queue_processor = load_module("sharepoint_queue_processor", "sharepoint_queue_processor.py")
housekeeping = load_module("sharepoint_housekeeping", "sharepoint_housekeeping.py")


class HousekeepingQueueProducerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.old_queue_processor = {
            "QUEUE_FILE": queue_processor.QUEUE_FILE,
            "LOCK_FILE": queue_processor.LOCK_FILE,
            "LOG_FILE": queue_processor.LOG_FILE,
        }
        self.old_housekeeping = {
            "STATE_DIR": housekeeping.STATE_DIR,
            "LOG_FILE": housekeeping.LOG_FILE,
        }
        queue_processor.QUEUE_FILE = root / "sharepoint-queue.json"
        queue_processor.LOCK_FILE = root / "sharepoint-queue.lock"
        queue_processor.LOG_FILE = root / "queue.log"
        housekeeping.STATE_DIR = root
        housekeeping.LOG_FILE = root / "housekeeping.log"

    def tearDown(self):
        for name, value in self.old_queue_processor.items():
            setattr(queue_processor, name, value)
        for name, value in self.old_housekeeping.items():
            setattr(housekeeping, name, value)
        self.tempdir.cleanup()

    def test_housekeeping_uses_locked_enqueue_contract(self):
        entity = {"name": "Acme", "type": "account"}
        decision = {
            "safe_changes": [
                {
                    "action": "update",
                    "path": "/Accounts/Acme/Acme - Current.md",
                    "content": "updated",
                    "reason": "normalise",
                }
            ],
            "ambiguous": [],
            "blocked": [],
        }

        submitted = housekeeping.execute_safe_changes(entity, decision)

        self.assertEqual(len(submitted), 1)
        self.assertEqual(json.loads(queue_processor.QUEUE_FILE.read_text()), submitted)

    def test_housekeeping_and_other_producers_do_not_lose_entries(self):
        count = 32
        barrier = threading.Barrier(count)
        errors = []

        def produce(index):
            try:
                barrier.wait()
                if index % 2 == 0:
                    entity = {"name": f"Account {index}", "type": "account"}
                    decision = {
                        "safe_changes": [
                            {
                                "action": "create",
                                "path": f"/Accounts/Account {index}/note.md",
                                "content": str(index),
                            }
                        ],
                        "ambiguous": [],
                        "blocked": [],
                    }
                    self.assertEqual(
                        len(housekeeping.execute_safe_changes(entity, decision)), 1
                    )
                else:
                    self.assertTrue(
                        queue_processor.enqueue_operation(
                            {
                                "id": f"other-producer-{index}",
                                "operation": "append",
                                "path": f"/Accounts/Other/note-{index}.md",
                                "content": str(index),
                            }
                        )
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=produce, args=(index,)) for index in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertFalse(errors)
        queued = json.loads(queue_processor.QUEUE_FILE.read_text())
        self.assertEqual(len(queued), count)
        self.assertEqual(len({entry["id"] for entry in queued}), count)


if __name__ == "__main__":
    unittest.main()
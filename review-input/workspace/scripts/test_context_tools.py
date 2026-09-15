#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent
PY = sys.executable


def run(script, *args):
    result = subprocess.run([PY, str(ROOT / script), *map(str, args)], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout


class ContextToolsTests(unittest.TestCase):
    def test_extract_is_bounded_and_targeted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.md"
            path.write_text("# One\nalpha\n## Two\nneedle here\n" + "x" * 500)
            output = run("context_extract.py", path, "--match", "needle", "--max-chars", 100)
            self.assertIn("needle", output)
            self.assertLessEqual(len(output), 160)

    def test_extract_cap_is_global_across_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "one.txt", Path(directory) / "two.txt"
            first.write_text("a" * 100)
            second.write_text("b" * 100)
            output = run("context_extract.py", first, second, "--max-chars", 80)
            self.assertLessEqual(len(output), 140)
            self.assertNotIn("b" * 20, output)

    def test_session_query_returns_bounded_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.jsonl"
            path.write_text(json.dumps({"type": "message", "id": "1", "timestamp": "t", "message": {"role": "user", "content": [{"type": "text", "text": "hello " + "z" * 500}]}}) + "\n")
            payload = json.loads(run("session_query.py", path, "hello", "--snippet-chars", 40))
            self.assertEqual(payload["matches"][0]["id"], "1")
            self.assertLessEqual(len(payload["matches"][0]["snippet"]), 43)

    def test_session_query_has_total_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.jsonl"
            records = [json.dumps({"id": str(index), "message": {"role": "user", "content": "needle " + "x" * 500}}) for index in range(10)]
            path.write_text("\n".join(records) + "\n")
            payload = json.loads(run("session_query.py", path, "needle", "--max-total-chars", 500))
            self.assertTrue(payload["truncated"])
            self.assertLess(len(json.dumps(payload["matches"])), 700)

    def test_dashboard_handles_openclaw_map(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"
            path.write_text(json.dumps({"k": {"model": "m", "contextTokens": 200000, "totalTokens": 10, "compactionCount": 2, "updatedAt": 3}}))
            rows = json.loads(run("context_dashboard.py", "--path", path))
            self.assertEqual(rows[0]["key"], "k")
            self.assertEqual(rows[0]["context_window"], 200000)

    def test_worker_bounds_success_and_timeout_output(self):
        success = json.loads(run("worker_wrapper.py", "--max-output", 20, "--", PY, "-c", "print('a' * 100); import sys; print('b' * 100, file=sys.stderr)"))
        self.assertEqual(success["status"], "success")
        self.assertTrue(success["truncated"])
        self.assertLessEqual(len(success["stdout"]), 40)
        timeout = json.loads(run("worker_wrapper.py", "--max-output", 20, "--timeout", "0.3", "--", PY, "-u", "-c", "import time; print('a' * 100, flush=True); time.sleep(1)"))
        self.assertEqual(timeout["status"], "timeout")
        self.assertTrue(timeout["truncated"])


if __name__ == "__main__":
    unittest.main()

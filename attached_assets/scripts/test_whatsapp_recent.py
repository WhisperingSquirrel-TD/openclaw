import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).with_name("whatsapp_recent.sh")


def write_transcript(home: Path, account_id: str, records: list[dict]) -> None:
    transcript_dir = home / ".openclaw" / "credentials" / "whatsapp" / "watch-transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    transcript = transcript_dir / f"whatsapp-watch-{account_id}.jsonl"
    transcript.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def run_recent(home: Path) -> tuple[dict, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TZ"] = "UTC"
    subprocess.run(["bash", str(SCRIPT)], check=True, env=env)
    workspace = home / ".openclaw" / "workspace"
    sidecar = json.loads(
        (workspace / "memory" / "whatsapp-recent-window.json").read_text(
            encoding="utf-8"
        )
    )
    recent = (workspace / "WHATSAPP_RECENT.md").read_text(encoding="utf-8")
    return sidecar, recent


def make_record(index: int, *, account_id: str = "default") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "messageId": f"{account_id}-{index}",
        "channel": "whatsapp",
        "chatType": "direct",
        "chatName": "Alice",
        "senderName": "Alice",
        "senderNumber": "+15551234567",
        "timestamp": (now - timedelta(minutes=index)).isoformat(),
        "body": f"message-{account_id}-{index}",
        "isFromMe": False,
    }


class WhatsAppRecentMirrorTests(unittest.TestCase):
    def test_recent_mirror_keeps_all_messages_below_global_retention_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            write_transcript(home, "default", [make_record(index) for index in range(10)])

            sidecar, recent = run_recent(home)

            self.assertEqual(sidecar["source_message_count"], 10)
            self.assertEqual(sidecar["retained_message_count"], 10)
            self.assertFalse(sidecar["truncated"])
            self.assertTrue(sidecar["coverage_complete"])
            for index in range(10):
                self.assertIn(f"message-default-{index}", recent)

    def test_recent_mirror_aggregates_all_watch_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            write_transcript(home, "default", [make_record(1)])
            write_transcript(home, "personal", [make_record(2, account_id="personal")])

            sidecar, recent = run_recent(home)

            self.assertEqual(sidecar["source_account_count"], 2)
            self.assertEqual(sidecar["source_message_count"], 2)
            self.assertEqual(sidecar["retained_message_count"], 2)
            self.assertTrue(sidecar["coverage_complete"])
            self.assertIn("message-default-1", recent)
            self.assertIn("message-personal-2", recent)


if __name__ == "__main__":
    unittest.main()

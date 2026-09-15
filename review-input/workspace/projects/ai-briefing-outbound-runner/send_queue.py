from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

SEND_SCRIPT = Path.home() / ".openclaw" / "integrations" / "microsoft-l1" / "send.py"
EMAIL_LOG_PATH = Path.home() / ".openclaw" / "workspace" / "memory" / "email_log.md"
TMP_DIR = Path("/tmp/ai-briefing-outbound-runner")


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def due_now(scheduled_send_at: str) -> bool:
    return parse_iso(scheduled_send_at) <= datetime.now(timezone.utc)


def prepare_send_files(outbound_id: int, recipient: str, subject: str, body: str) -> tuple[Path, Path, Path]:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    recipients_file = TMP_DIR / f"outbound-{outbound_id}-recipients.txt"
    subject_file = TMP_DIR / f"outbound-{outbound_id}-subject.txt"
    body_file = TMP_DIR / f"outbound-{outbound_id}-body.txt"
    recipients_file.write_text(recipient + "\n", encoding="utf-8")
    subject_file.write_text(subject + "\n", encoding="utf-8")
    body_file.write_text(body, encoding="utf-8")
    return recipients_file, subject_file, body_file


def build_send_command(outbound_id: int, recipient: str, subject: str, body: str,
                       account: str = "assistant", from_name: str = "PA to Tom Dean") -> list[str]:
    recipients_file, subject_file, body_file = prepare_send_files(outbound_id, recipient, subject, body)
    return [
        "python3",
        str(SEND_SCRIPT),
        "--account", account,
        "--recipients-file", str(recipients_file),
        "--subject-file", str(subject_file),
        "--body-file", str(body_file),
        recipient,
        from_name,
    ]


def execute_send_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=60)


def append_email_log(recipient: str, subject: str, status: str) -> None:
    EMAIL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    line = f"- {ts} | assistant@ | {recipient} | {subject} | {status}\n"
    with EMAIL_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)

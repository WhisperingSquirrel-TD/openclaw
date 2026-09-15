from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SEND_SCRIPT = Path.home() / ".openclaw" / "integrations" / "microsoft-l1" / "send.py"
EMAIL_LOG_PATH = Path.home() / ".openclaw" / "workspace" / "memory" / "email_log.md"
TMP_DIR = Path("/tmp/ai-briefing-outbound-runner")
CANDIDATE_SENT_SURFACES = [
    Path.home() / ".openclaw" / "workspace" / "OUTLOOK_SENT.md",
    Path.home() / ".openclaw" / "workspace" / "MICROSOFT_SENT.md",
]
MSG_ID_RE = re.compile(r"\b([A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|msg[a-zA-Z0-9_-]+)\b")


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


def build_send_command(outbound_id: int, recipient: str, subject: str, body: str, account: str = "assistant", from_name: str = "PA to Tom Dean") -> list[str]:
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


def extract_provider_message_id(stdout: str, stderr: str) -> str | None:
    text = f"{stdout}\n{stderr}".strip()
    for match in MSG_ID_RE.findall(text):
        return match
    return None


def verify_from_sent_surfaces(recipient: str, subject: str) -> tuple[bool, str]:
    for surface in CANDIDATE_SENT_SURFACES:
        if not surface.exists():
            continue
        txt = surface.read_text(encoding="utf-8", errors="ignore")
        if recipient in txt and subject in txt:
            return True, f"Verified via {surface.name}"
    return False, "No Sent Items evidence found in local sent surfaces"


def append_email_log(recipient: str, subject: str, status: str) -> None:
    EMAIL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    line = f"- {ts} | assistant@ | {recipient} | {subject} | {status}\n"
    with EMAIL_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)

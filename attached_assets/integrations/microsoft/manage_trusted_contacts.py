#!/usr/bin/env python3
"""Protected operator tool for the canonical trusted-contact registry.

Mutation is intentionally narrow: this tool accepts only add/remove/list, uses
one fixed canonical path, requires root for mutation, and maintains the
filesystem immutable/read-only lock around every change. The caller must invoke
it through the TOTP-gated exec route; this script is not a general file editor.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import re
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

OPERATOR_HOME = Path("/home/tomdean88")
CONTACTS_FILE = OPERATOR_HOME / ".openclaw/integrations/known-contacts.txt"
AUDIT_FILE = OPERATOR_HOME / ".openclaw/integrations/trusted-contacts-audit.log"
LOCK_FILE = Path("/tmp/openclaw-trusted-contacts.lock")
FS_IOC_GETFLAGS = 0x80086601
FS_IOC_SETFLAGS = 0x40086602
FS_IMMUTABLE_FL = 0x10
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def fail(message: str, code: int = 2) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def normalise_email(raw: str) -> str:
    value = raw.strip().lower()
    if not EMAIL_RE.fullmatch(value):
        fail("email must be a single valid address")
    return value


def read_entries() -> tuple[list[str], list[str]]:
    if not CONTACTS_FILE.exists():
        fail(f"canonical registry missing: {CONTACTS_FILE}")
    if CONTACTS_FILE.is_symlink():
        fail("canonical registry is a symlink")
    lines = CONTACTS_FILE.read_text(encoding="utf-8").splitlines()
    entries = [line.strip().lower() for line in lines
               if line.strip() and not line.lstrip().startswith("#")]
    return lines, entries


def set_immutable(enabled: bool) -> None:
    fd = os.open(CONTACTS_FILE, os.O_RDONLY)
    try:
        buf = bytearray(4)
        fcntl.ioctl(fd, FS_IOC_GETFLAGS, buf, True)
        flags = struct.unpack("I", buf)[0]
        wanted = (flags | FS_IMMUTABLE_FL) if enabled else (flags & ~FS_IMMUTABLE_FL)
        fcntl.ioctl(fd, FS_IOC_SETFLAGS, struct.pack("I", wanted))
    finally:
        os.close(fd)


def audit(action: str, email: str, before: list[str], after: list[str]) -> None:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    AUDIT_FILE.open("a", encoding="utf-8").write(
        f"{ts} action={action} email={email or '-'} "
        f"before_count={len(before)} after_count={len(after)}\n"
    )


def list_contacts() -> None:
    _, entries = read_entries()
    for entry in entries:
        print(entry)


def mutate(action: str, email: str) -> None:
    if os.geteuid() != 0:
        fail("mutations require the protected root/TOTP execution route", 1)
    email = normalise_email(email)
    LOCK_FILE.touch(exist_ok=True)
    with LOCK_FILE.open("r+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        lines, before = read_entries()
        present = email in before
        if action == "add" and present:
            fail(f"already present: {email}", 3)
        if action == "remove" and not present:
            fail(f"not present: {email}", 3)
        try:
            set_immutable(False)
            if action == "add":
                lines.append(email)
            else:
                lines = [line for line in lines if line.strip().lower() != email]
            content = "\n".join(lines).rstrip("\n") + "\n"
            CONTACTS_FILE.write_text(content, encoding="utf-8")
            os.chmod(CONTACTS_FILE, 0o444)
            _, after = read_entries()
            if action == "add" and email not in after:
                fail("post-write verification failed: entry missing")
            if action == "remove" and email in after:
                fail("post-write verification failed: entry remains")
            audit(action, email, before, after)
        finally:
            os.chmod(CONTACTS_FILE, 0o444)
            set_immutable(True)
        print(f"OK: {action} {email}; entries={len(after)}; registry relocked")


def main() -> int:
    parser = argparse.ArgumentParser(description="Protected trusted-contact registry tool")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="list the canonical trusted contacts")
    for action in ("add", "remove"):
        cmd = sub.add_parser(action, help=f"{action} one trusted contact")
        cmd.add_argument("email")
    args = parser.parse_args()
    if args.action == "list":
        list_contacts()
    else:
        mutate(args.action, args.email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

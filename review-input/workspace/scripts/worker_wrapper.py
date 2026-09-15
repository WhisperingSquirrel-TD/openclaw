#!/usr/bin/env python3
"""Run an argv command and return bounded JSON output.

Child output is written to temporary files, so a noisy process cannot first fill
this process's memory and then be truncated only after the fact.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def bounded_file(path: Path, limit: int, full: bool) -> tuple[str, bool, int]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if full or size <= limit:
            data = handle.read()
            return data.decode("utf-8", errors="replace"), False, size
        # Preserve the start because command diagnostics normally lead there.
        data = handle.read(limit)
        return data.decode("utf-8", errors="replace") + "\n[output truncated]", True, size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-output", type=positive, default=10000,
                        help="total stdout+stderr character budget (default: 10000)")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--full-output", action="store_true", help="intentional unbounded output")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="use -- before the command argv")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide an argv command after --")

    started = time.monotonic()
    # Split the normal budget evenly so a huge stdout cannot hide a useful error.
    stream_limit = args.max_output if args.full_output else max(1, args.max_output // 2)
    try:
        with tempfile.TemporaryDirectory(prefix="openclaw-worker-") as directory:
            stdout_path = Path(directory) / "stdout"
            stderr_path = Path(directory) / "stderr"
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr, shell=False)
                try:
                    exit_code = process.wait(timeout=args.timeout)
                    status = "success" if exit_code == 0 else "failed"
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    exit_code, status = None, "timeout"
            stdout, stdout_truncated, stdout_bytes = bounded_file(stdout_path, stream_limit, args.full_output)
            stderr, stderr_truncated, stderr_bytes = bounded_file(stderr_path, stream_limit, args.full_output)
            payload = {
                "status": status,
                "exit_code": exit_code,
                "duration_seconds": round(time.monotonic() - started, 3),
                "stdout": stdout,
                "stderr": stderr,
                "truncated": stdout_truncated or stderr_truncated,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "stdout_bytes": stdout_bytes,
                "stderr_bytes": stderr_bytes,
            }
    except OSError as exc:
        error = str(exc)[:args.max_output]
        payload = {
            "status": "error", "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": "", "stderr": error,
            "truncated": len(str(exc)) > len(error),
            "stdout_truncated": False, "stderr_truncated": len(str(exc)) > len(error),
            "stdout_bytes": 0, "stderr_bytes": len(str(exc).encode("utf-8", errors="replace")),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

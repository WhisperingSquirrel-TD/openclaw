#!/usr/bin/env python3
"""Bounded context inspection: report file metadata and optional targeted matches.
Never emits a whole file. Use before deciding how to read a large artifact.
"""
from __future__ import annotations
import argparse, json, re
from datetime import datetime
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("paths", nargs="+", type=Path)
p.add_argument("--match", help="regex to search")
p.add_argument("--max-matches", type=int, default=20)
p.add_argument("--max-bytes", type=int, default=2_000_000)
a = p.parse_args()
rx = re.compile(a.match, re.I) if a.match else None
out = []
for path in a.paths:
    item = {"path": str(path)}
    if not path.exists():
        item["state"] = "missing"
        out.append(item)
        continue
    st = path.stat()
    item.update({
        "state": "present",
        "bytes": st.st_size,
        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    })
    if rx and st.st_size <= a.max_bytes:
        matches = []
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for number, line in enumerate(f, 1):
                if rx.search(line):
                    matches.append({"line": number, "text": line.rstrip()[:1000]})
                    if len(matches) >= a.max_matches:
                        break
        item["matches"] = matches
        item["match_truncated"] = len(matches) >= a.max_matches
    elif rx:
        item["matches"] = []
        item["match_state"] = "skipped_over_max_bytes"
    out.append(item)
print(json.dumps(out, ensure_ascii=False, indent=2))

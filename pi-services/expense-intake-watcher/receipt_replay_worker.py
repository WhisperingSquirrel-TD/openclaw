#!/usr/bin/env python3
"""Run only the bounded durable receipt-replay delivery path.

This is intentionally separate from the broad mirror watcher so receipt evidence
can be completed promptly without reprocessing mailbox/chat feeds.
"""
from __future__ import annotations

import json

from watcher import process_expense_sqlite_replay


def main() -> int:
    results = process_expense_sqlite_replay({})
    print(json.dumps(results, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

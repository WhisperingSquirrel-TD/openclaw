#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/pi-services/seer-finance${PYTHONPATH:+:$PYTHONPATH}"
(cd "$ROOT/pi-services/seer-finance" && python3 -m unittest discover -s tests -p 'test_*.py' -v)
(cd "$ROOT/pi-services/expense-intake-watcher" && python3 -m unittest discover -s . -p 'test_*.py' -v)

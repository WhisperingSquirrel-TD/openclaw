#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/pi-services/seer-finance${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest discover -s "$ROOT/pi-services/seer-finance/tests" -p 'test_*.py' -v
python3 -m unittest discover -s "$ROOT/pi-services/expense-intake-watcher" -p 'test_*.py' -v

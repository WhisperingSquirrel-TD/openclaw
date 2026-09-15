#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tomdean88/.openclaw/workspace/projects/workspace-control-panel"
RUNTIME_DIR="$PROJECT_DIR/.runtime"
LOG_FILE="$RUNTIME_DIR/wcp-tunnel.log"
URL_FILE="$RUNTIME_DIR/wcp-tunnel-url.txt"

if [ -f "$URL_FILE" ] && [ -s "$URL_FILE" ]; then
  cat "$URL_FILE"
  exit 0
fi

if [ -f "$LOG_FILE" ]; then
  URL=$(grep -o 'https://[-a-zA-Z0-9.]*trycloudflare.com' "$LOG_FILE" | tail -1 || true)
  if [ -n "${URL:-}" ]; then
    printf '%s\n' "$URL" > "$URL_FILE"
    echo "$URL"
    exit 0
  fi
fi

echo "No quick tunnel URL found. Start the tunnel first." >&2
exit 1

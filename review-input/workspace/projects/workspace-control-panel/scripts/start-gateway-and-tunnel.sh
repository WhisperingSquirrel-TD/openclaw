#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tomdean88/.openclaw/workspace/projects/workspace-control-panel"
RUNTIME_DIR="$PROJECT_DIR/.runtime"
LOG_FILE="$RUNTIME_DIR/wcp-tunnel.log"
URL_FILE="$RUNTIME_DIR/wcp-tunnel-url.txt"
PID_FILE="$RUNTIME_DIR/wcp-tunnel.pid"
GATEWAY_HEALTH="http://127.0.0.1:4312/health"

mkdir -p "$RUNTIME_DIR"

# Make sure the gateway service is up first.
systemctl --user restart workspace-pi-gateway.service

for _ in $(seq 1 20); do
  if curl -fsS "$GATEWAY_HEALTH" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "$GATEWAY_HEALTH" >/dev/null 2>&1; then
  echo "Gateway did not come up on 127.0.0.1:4312" >&2
  exit 1
fi

# Stop an old tunnel process if we have one recorded.
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
fi

rm -f "$LOG_FILE" "$URL_FILE"

nohup cloudflared tunnel --url http://localhost:4312 > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

# Wait for the URL to appear in the log.
for _ in $(seq 1 30); do
  URL=$(grep -o 'https://[-a-zA-Z0-9.]*trycloudflare.com' "$LOG_FILE" 2>/dev/null | tail -1 || true)
  if [ -n "${URL:-}" ]; then
    printf '%s\n' "$URL" > "$URL_FILE"
    echo "Gateway service OK"
    echo "Tunnel PID: $NEW_PID"
    echo "Tunnel URL: $URL"
    exit 0
  fi
  sleep 1
done

echo "Tunnel started (PID $NEW_PID) but URL was not detected yet. Check $LOG_FILE" >&2
exit 1

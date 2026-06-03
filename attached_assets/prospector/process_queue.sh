#!/usr/bin/env bash
# process_queue.sh — bounce/unsub queue processor for OpenClaw prospector
# Runs every 30 minutes via cron. Reads pending_bounces.txt and
# pending_unsubs.txt, calls manage.py for each address, then clears the files.
#
# Cron (installed by install-forked-openclaw.sh):
#   */30 * * * * bash ~/prospector/process_queue.sh >> ~/prospector/logs/queue_processor.log 2>&1

PROSPECTOR_DIR="$HOME/prospector"
MANAGE="$PROSPECTOR_DIR/manage.py"
BOUNCES_FILE="$PROSPECTOR_DIR/pending_bounces.txt"
UNSUBS_FILE="$PROSPECTOR_DIR/pending_unsubs.txt"
LOG_DIR="$PROSPECTOR_DIR/logs"
LOG_FILE="$LOG_DIR/queue_processor.log"
CONFIG_FILE="$PROSPECTOR_DIR/config.json"

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

get_webhook() {
    python3 - <<'PY'
import json, os
config_path = os.path.expanduser('/home/tomdean88/prospector/config.json')
try:
    with open(config_path) as f:
        cfg = json.load(f)
    print(cfg.get('discord_bounces_webhook', '').strip())
except Exception:
    print('')
PY
}

DISCORD_BOUNCES_WEBHOOK="$(get_webhook)"

post_discord() {
    local message="$1"
    [ -z "$DISCORD_BOUNCES_WEBHOOK" ] && return 0
    python3 - "$DISCORD_BOUNCES_WEBHOOK" "$message" >> "$LOG_FILE" 2>&1 <<'PY'
import json, sys, urllib.request
webhook = sys.argv[1]
message = sys.argv[2]
if not webhook or not message.strip():
    raise SystemExit(0)
payload = json.dumps({"content": message}).encode('utf-8')
req = urllib.request.Request(webhook, data=payload, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=15) as resp:
    print(f"Discord post status: {resp.status}")
PY
}

echo "[$(ts)] Queue processor started" >> "$LOG_FILE"

# Process bounces
if [ -s "$BOUNCES_FILE" ]; then
    BOUNCE_COUNT=0
    BOUNCE_LINES=""
    while IFS= read -r email; do
        email="$(echo "$email" | tr -d '[:space:]')"
        [ -z "$email" ] && continue
        echo "[$(ts)] BOUNCE: $email" >> "$LOG_FILE"
        python3 "$MANAGE" bounce "$email" >> "$LOG_FILE" 2>&1
        BOUNCE_COUNT=$((BOUNCE_COUNT + 1))
        BOUNCE_LINES+="• $email\n"
    done < "$BOUNCES_FILE"
    > "$BOUNCES_FILE"
    if [ "$BOUNCE_COUNT" -gt 0 ]; then
        post_discord "**Bounce queue processed — $(date '+%d/%m/%Y %H:%M')**

${BOUNCE_LINES}
Queued via prospector/process_queue.sh"
    fi
    echo "[$(ts)] Processed $BOUNCE_COUNT bounce(s). File cleared." >> "$LOG_FILE"
else
    echo "[$(ts)] No pending bounces." >> "$LOG_FILE"
fi

# Process unsubscribes
if [ -s "$UNSUBS_FILE" ]; then
    UNSUB_COUNT=0
    UNSUB_LINES=""
    while IFS= read -r email; do
        email="$(echo "$email" | tr -d '[:space:]')"
        [ -z "$email" ] && continue
        echo "[$(ts)] UNSUB: $email" >> "$LOG_FILE"
        python3 "$MANAGE" unsub "$email" >> "$LOG_FILE" 2>&1
        UNSUB_COUNT=$((UNSUB_COUNT + 1))
        UNSUB_LINES+="• $email\n"
    done < "$UNSUBS_FILE"
    > "$UNSUBS_FILE"
    if [ "$UNSUB_COUNT" -gt 0 ]; then
        post_discord "**Unsubscribe queue processed — $(date '+%d/%m/%Y %H:%M')**

${UNSUB_LINES}
Queued via prospector/process_queue.sh"
    fi
    echo "[$(ts)] Processed $UNSUB_COUNT unsub(s). File cleared." >> "$LOG_FILE"
else
    echo "[$(ts)] No pending unsubscribes." >> "$LOG_FILE"
fi

echo "[$(ts)] Queue processor finished." >> "$LOG_FILE"

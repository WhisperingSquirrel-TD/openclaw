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

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts)] Queue processor started" >> "$LOG_FILE"

# Process bounces
if [ -s "$BOUNCES_FILE" ]; then
    BOUNCE_COUNT=0
    while IFS= read -r email; do
        email="$(echo "$email" | tr -d '[:space:]')"
        [ -z "$email" ] && continue
        echo "[$(ts)] BOUNCE: $email" >> "$LOG_FILE"
        python3 "$MANAGE" bounce "$email" >> "$LOG_FILE" 2>&1
        BOUNCE_COUNT=$((BOUNCE_COUNT + 1))
    done < "$BOUNCES_FILE"
    > "$BOUNCES_FILE"
    echo "[$(ts)] Processed $BOUNCE_COUNT bounce(s). File cleared." >> "$LOG_FILE"
else
    echo "[$(ts)] No pending bounces." >> "$LOG_FILE"
fi

# Process unsubscribes
if [ -s "$UNSUBS_FILE" ]; then
    UNSUB_COUNT=0
    while IFS= read -r email; do
        email="$(echo "$email" | tr -d '[:space:]')"
        [ -z "$email" ] && continue
        echo "[$(ts)] UNSUB: $email" >> "$LOG_FILE"
        python3 "$MANAGE" unsub "$email" >> "$LOG_FILE" 2>&1
        UNSUB_COUNT=$((UNSUB_COUNT + 1))
    done < "$UNSUBS_FILE"
    > "$UNSUBS_FILE"
    echo "[$(ts)] Processed $UNSUB_COUNT unsub(s). File cleared." >> "$LOG_FILE"
else
    echo "[$(ts)] No pending unsubscribes." >> "$LOG_FILE"
fi

echo "[$(ts)] Queue processor finished." >> "$LOG_FILE"

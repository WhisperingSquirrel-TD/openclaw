#!/usr/bin/env bash
# whatsapp_recent.sh — generates a rolling 48-hour view of WHATSAPP_LOG.md
# Runs every 15 minutes via cron (installed by install-forked-openclaw.sh).
#
# Source:  ~/.openclaw/workspace/WHATSAPP_LOG.md  (full append-only log)
# Output:  ~/.openclaw/workspace/WHATSAPP_RECENT.md  (last 48h, L1 reads this)
#
# Format of each log line:
#   [YYYY-MM-DD HH:MM] optional-group-name sender: body
#
# Recent-view normalization:
#   - direct inbound stays:  [ts] Lauren: hi
#   - direct outbound rewrites ambiguous `Me:` to: [ts] Tom -> Lauren: hi
#   - group outbound stays group-scoped: [ts] [Family] Me: hi
#
# Note: the full log remains append-only source data; this script adds thread-explicit
# direct-outbound labels in WHATSAPP_RECENT.md for safer downstream monitoring.

WORKSPACE="$HOME/.openclaw/workspace"
SOURCE_LOG="$WORKSPACE/WHATSAPP_LOG.md"
RECENT_MD="$WORKSPACE/WHATSAPP_RECENT.md"
HOURS=48
MAX_LINES=400

if [ ! -f "$SOURCE_LOG" ]; then
    exit 0
fi

# Cutoff timestamp — 48 hours ago in YYYY-MM-DD HH:MM format (comparable to log prefix)
CUTOFF=$(date -d "${HOURS} hours ago" '+%Y-%m-%d %H:%M' 2>/dev/null \
         || date -v-${HOURS}H '+%Y-%m-%d %H:%M' 2>/dev/null)  # macOS fallback

if [ -z "$CUTOFF" ]; then
    # Can't determine cutoff — fall back to tail
    RECENT=$(tail -n "$MAX_LINES" "$SOURCE_LOG")
else
    # Keep lines whose timestamp prefix is >= CUTOFF
    # Lines without a timestamp prefix (continuation lines) are kept if the previous
    # timestamped line was within the window — but since each WhatsApp message is one
    # line, a simple timestamp filter is sufficient.
    RECENT=$(grep -E '^\[20[0-9]{2}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}\]' "$SOURCE_LOG" \
             | awk -v cutoff="$CUTOFF" '{ ts=substr($0,2,16); if (ts >= cutoff) print }')

    # Safety cap: if the time-filtered result is still huge, take the last MAX_LINES
    LINE_COUNT=$(echo "$RECENT" | wc -l)
    if [ "$LINE_COUNT" -gt "$MAX_LINES" ]; then
        RECENT=$(echo "$RECENT" | tail -n "$MAX_LINES")
    fi
fi

if [ -n "$RECENT" ]; then
    # Rewrite ambiguous direct outbound `Me:` lines into an explicit thread form for
    # downstream readers. We only rewrite non-group lines; group lines keep their
    # existing `[Group] Me:` shape. Heuristic: direct-chat context follows the most
    # recent direct inbound sender visible in the recent slice.
    RECENT=$(printf '%s\n' "$RECENT" | awk '
        function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }
        {
            line = $0
            rest = line
            sub(/^\[[0-9-]+ [0-9:]+\][[:space:]]*/, "", rest)

            if (rest ~ /^\[[^]]+\][[:space:]]+Me:[[:space:]]*/) {
                print line
                next
            }

            if (rest ~ /^\[[^]]+\][[:space:]]+/) {
                print line
                next
            }

            if (rest ~ /^Me:[[:space:]]*/) {
                if (last_direct_contact != "") {
                    sub(/Me:/, "Tom -> " last_direct_contact ":", line)
                } else {
                    sub(/Me:/, "Tom -> Direct chat:", line)
                }
                print line
                next
            }

            split(rest, parts, ":")
            sender = trim(parts[1])
            if (sender != "") {
                last_direct_contact = sender
            }
            print line
        }
    ')
fi

if [ -z "$RECENT" ]; then
    RECENT="_(no messages in the last ${HOURS} hours)_"
fi

UPDATED=$(date '+%Y-%m-%d %H:%M')

cat > "$RECENT_MD" << EOF
# WhatsApp Recent (last ${HOURS}h)
_Updated: ${UPDATED} — showing last ${HOURS} hours (max ${MAX_LINES} lines). Full log: WHATSAPP_LOG.md_

${RECENT}
EOF

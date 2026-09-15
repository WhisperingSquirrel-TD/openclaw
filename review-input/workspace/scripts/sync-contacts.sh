#!/bin/bash
# sync-contacts.sh
# Reads contacts.md, extracts phone numbers, syncs them to allowFrom in openclaw.json
# Requires passwordless sudo for chattr on the config file (see sudoers setup)

set -euo pipefail

WORKSPACE="/home/tomdean88/.openclaw/workspace"
CONFIG="/home/tomdean88/.openclaw/openclaw.json"
CONTACTS_FILE="$WORKSPACE/contacts.md"

echo "[sync-contacts] Starting..."

# Extract all E.164 numbers from contacts.md
NUMBERS_RAW=$(grep -oP '\+\d{10,15}' "$CONTACTS_FILE" | sort -u)

if [ -z "$NUMBERS_RAW" ]; then
    echo "[sync-contacts] ERROR: No phone numbers found in $CONTACTS_FILE"
    exit 1
fi

echo "[sync-contacts] Found numbers:"
echo "$NUMBERS_RAW"

# Build JSON array from the numbers
JSON_ARRAY=$(echo "$NUMBERS_RAW" | node -e "
  const lines = [];
  const rl = require('readline').createInterface({ input: process.stdin });
  rl.on('line', l => { if (l.trim()) lines.push(l.trim()); });
  rl.on('close', () => console.log(JSON.stringify(lines)));
")

echo "[sync-contacts] JSON array: $JSON_ARRAY"

# Remove immutable flag (sudoers allows this without password)
echo "[sync-contacts] Removing immutable flag..."
sudo /usr/bin/chattr -i "$CONFIG"

# Update allowFrom in the config using Node.js
node -e "
  const fs = require('fs');
  const raw = fs.readFileSync('$CONFIG', 'utf8');
  const config = JSON.parse(raw);
  const numbers = $JSON_ARRAY;
  config.channels = config.channels || {};
  config.channels.whatsapp = config.channels.whatsapp || {};
  config.channels.whatsapp.allowFrom = numbers;
  fs.writeFileSync('$CONFIG', JSON.stringify(config, null, 2));
  console.log('[sync-contacts] Updated allowFrom with ' + numbers.length + ' numbers: ' + numbers.join(', '));
"

# Re-add immutable flag
echo "[sync-contacts] Restoring immutable flag..."
sudo /usr/bin/chattr +i "$CONFIG"

# Restart gateway to apply
echo "[sync-contacts] Restarting gateway..."
openclaw gateway restart

echo "[sync-contacts] Done."

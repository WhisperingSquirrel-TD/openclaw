#!/usr/bin/env bash
# set-env.sh — update a single key in ~/.openclaw/.env
# Usage:
#   set-env.sh KEY value
#   set-env.sh OPENCLAW_OPENAI_MODEL gpt-5-mini-2025-08-07
#   set-env.sh GARMIN_PASSWORD mysecretpassword

ENV_FILE="$HOME/.openclaw/.env"

if [ $# -ne 2 ]; then
    echo "Usage: set-env.sh KEY value"
    echo "Example: set-env.sh OPENCLAW_OPENAI_MODEL gpt-5-mini-2025-08-07"
    exit 1
fi

KEY="$1"
VAL="$2"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found"
    exit 1
fi

# If key already exists (with or without export prefix), replace the whole line
if grep -qE "^(export )?${KEY}=" "$ENV_FILE"; then
    sed -i "s|^\\(export \\)\\{0,1\\}${KEY}=.*|export ${KEY}=${VAL}|" "$ENV_FILE"
    echo "Updated: ${KEY}=${VAL}"
else
    echo "export ${KEY}=${VAL}" >> "$ENV_FILE"
    echo "Added: ${KEY}=${VAL}"
fi

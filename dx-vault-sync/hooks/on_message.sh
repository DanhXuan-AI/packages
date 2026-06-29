#!/usr/bin/env bash
# DX Vault Sync — Notification hook for Claude Code
# Triggers incremental learning every N messages.
# Claude Code passes JSON payload on stdin.
#
# Hook event: Notification

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="${SCRIPT_DIR}/../scripts/sync_engine.py"
VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/ObsidianVault}"
COUNTER_FILE="${SCRIPT_DIR}/../.message_counter"
LEARN_INTERVAL="${DX_LEARN_INTERVAL:-6}"

PAYLOAD=""
if ! [ -t 0 ]; then
    PAYLOAD=$(cat 2>/dev/null || true)
fi

COUNT=0
if [ -f "$COUNTER_FILE" ]; then
    COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
fi

COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

if [ $((COUNT % LEARN_INTERVAL)) -eq 0 ]; then
    if [ -n "$PAYLOAD" ]; then
        MESSAGE=$(echo "$PAYLOAD" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('message', data.get('content', data.get('text', ''))))
except: pass
" 2>/dev/null || true)

        if [ -n "$MESSAGE" ] && [ ${#MESSAGE} -gt 30 ]; then
            python3 "$SYNC_SCRIPT" --vault "$VAULT_PATH" sync \
                --text "$MESSAGE" \
                --source "live-learn:msg-$COUNT" >/dev/null 2>&1 &
        fi
    fi
fi

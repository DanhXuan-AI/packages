#!/usr/bin/env bash
# DX Vault Sync — On-message hook for Claude Code
# Triggers incremental learning every N messages.
# Extracts quick insights without waiting for conversation end.
#
# Install: Add to Claude Code settings.json hooks.on_message

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="${SCRIPT_DIR}/../scripts/sync_engine.py"
VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/ObsidianVault}"
COUNTER_FILE="${SCRIPT_DIR}/../.message_counter"
LEARN_INTERVAL="${DX_LEARN_INTERVAL:-6}"

COUNT=0
if [ -f "$COUNTER_FILE" ]; then
    COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
fi

COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

if [ $((COUNT % LEARN_INTERVAL)) -eq 0 ]; then
    if [ -n "${CLAUDE_LAST_MESSAGE:-}" ]; then
        python3 "$SYNC_SCRIPT" --vault "$VAULT_PATH" sync \
            --text "$CLAUDE_LAST_MESSAGE" \
            --source "live-learn:msg-$COUNT" 2>/dev/null &
    fi
fi

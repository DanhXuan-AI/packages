#!/usr/bin/env bash
# DX Vault Sync — SessionStart hook for Claude Code
# Loads vault context and injects into session.
# Outputs context text to stdout for Claude Code to consume.
#
# Hook event: SessionStart (or manual pre-conversation)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMO_BRIDGE="${SCRIPT_DIR}/../scripts/memo_bridge.py"
VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/ObsidianVault}"

CONTEXT_CACHE="${SCRIPT_DIR}/../.vault_context.md"

if [ -f "$CONTEXT_CACHE" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$CONTEXT_CACHE" 2>/dev/null || stat -f %m "$CONTEXT_CACHE" 2>/dev/null || echo 0) ))
    if [ "$AGE" -lt 3600 ]; then
        cat "$CONTEXT_CACHE"
        exit 0
    fi
fi

python3 "$MEMO_BRIDGE" --vault "$VAULT_PATH" inject > "$CONTEXT_CACHE" 2>/dev/null
cat "$CONTEXT_CACHE" 2>/dev/null || echo "# DX Vault — Context unavailable"

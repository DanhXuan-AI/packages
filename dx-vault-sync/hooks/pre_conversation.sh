#!/usr/bin/env bash
# DX Vault Sync — Pre-conversation hook for Claude Code
# Loads relevant context from Obsidian Vault before each conversation.
# Outputs context summary to be injected into the session.
#
# Install: Add to Claude Code settings.json hooks.pre_conversation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="${SCRIPT_DIR}/../scripts/sync_engine.py"
VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/ObsidianVault}"

CONTEXT_FILE="${SCRIPT_DIR}/../.vault_context.md"

if [ -f "$CONTEXT_FILE" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$CONTEXT_FILE" 2>/dev/null || stat -f %m "$CONTEXT_FILE" 2>/dev/null || echo 0) ))
    if [ "$AGE" -lt 3600 ]; then
        cat "$CONTEXT_FILE"
        exit 0
    fi
fi

python3 "$SYNC_SCRIPT" --vault "$VAULT_PATH" context --output "$CONTEXT_FILE" 2>/dev/null
cat "$CONTEXT_FILE" 2>/dev/null || echo "# DX Vault — No context loaded"

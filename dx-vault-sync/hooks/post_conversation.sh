#!/usr/bin/env bash
# DX Vault Sync — Post-conversation hook for Claude Code
# Automatically extracts insights and syncs to Obsidian Vault
# after each Claude Code conversation ends.
#
# Install: Add to Claude Code settings.json hooks.post_conversation
# Or symlink to ~/.claude/hooks/post_conversation.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="${SCRIPT_DIR}/../scripts/sync_engine.py"
VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/ObsidianVault}"
LOG_DIR="${SCRIPT_DIR}/../logs"
LOG_FILE="${LOG_DIR}/sync_$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

log "Post-conversation hook triggered"

if [ -n "${CLAUDE_SESSION_DIR:-}" ] && [ -d "$CLAUDE_SESSION_DIR" ]; then
    log "Syncing session: $CLAUDE_SESSION_DIR"
    python3 "$SYNC_SCRIPT" --vault "$VAULT_PATH" sync --session "$CLAUDE_SESSION_DIR" >> "$LOG_FILE" 2>&1
    log "Session sync complete"

elif [ -n "${CLAUDE_CONVERSATION_TEXT:-}" ]; then
    log "Syncing conversation text"
    python3 "$SYNC_SCRIPT" --vault "$VAULT_PATH" sync --text "$CLAUDE_CONVERSATION_TEXT" >> "$LOG_FILE" 2>&1
    log "Text sync complete"

else
    log "No session or conversation data available, skipping"
fi

CONTEXT_OUTPUT="${SCRIPT_DIR}/../.vault_context.md"
python3 "$SYNC_SCRIPT" --vault "$VAULT_PATH" context --output "$CONTEXT_OUTPUT" >> "$LOG_FILE" 2>&1
log "Context refreshed at $CONTEXT_OUTPUT"

#!/usr/bin/env bash
# DX Vault Sync — Stop hook for Claude Code
# Auto-syncs conversation to vault + refreshes context + runs memo tick.
# Claude Code passes JSON payload on stdin with transcript_path.
#
# Hook event: Stop

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="${SCRIPT_DIR}/../scripts/sync_engine.py"
MEMO_BRIDGE="${SCRIPT_DIR}/../scripts/memo_bridge.py"
VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/ObsidianVault}"
LOG_DIR="${SCRIPT_DIR}/../logs"
LOG_FILE="${LOG_DIR}/sync_$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

log "Stop hook triggered (project: ${PWD})"

PAYLOAD=""
if ! [ -t 0 ]; then
    PAYLOAD=$(cat 2>/dev/null || true)
fi

TRANSCRIPT=""
if [ -n "$PAYLOAD" ]; then
    TRANSCRIPT=$(echo "$PAYLOAD" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('transcript_path', data.get('session_dir', '')))
except: pass
" 2>/dev/null || true)
fi

if [ -n "$TRANSCRIPT" ] && [ -e "$TRANSCRIPT" ]; then
    if [ -d "$TRANSCRIPT" ]; then
        log "Syncing session dir: $TRANSCRIPT"
        python3 "$SYNC_SCRIPT" --vault "$VAULT_PATH" sync --session "$TRANSCRIPT" >> "$LOG_FILE" 2>&1
    elif [ -f "$TRANSCRIPT" ]; then
        log "Syncing transcript file: $TRANSCRIPT"
        python3 "$SYNC_SCRIPT" --vault "$VAULT_PATH" sync --file "$TRANSCRIPT" >> "$LOG_FILE" 2>&1
    fi
    log "Transcript sync complete"
else
    log "No transcript available, refreshing context only"
fi

log "Running memo tick (context refresh + gap check)"
python3 "$MEMO_BRIDGE" --vault "$VAULT_PATH" tick >> "$LOG_FILE" 2>&1
log "Memo tick complete"

echo "0" > "${SCRIPT_DIR}/../.message_counter" 2>/dev/null || true
log "Message counter reset"

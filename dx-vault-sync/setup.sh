#!/usr/bin/env bash
# DX Vault Sync — Quick Setup Script
# Run: bash setup.sh [vault_path]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_PATH="${1:-${OBSIDIAN_VAULT_PATH:-$HOME/ObsidianVault}}"

echo "DX Vault Sync — Setup"
echo "====================="
echo "Vault path: $VAULT_PATH"
echo ""

echo "[1/5] Creating vault directories..."
mkdir -p "$VAULT_PATH/DX-Memory"/{conversations,decisions,entities,learnings,tasks,context,_index,_templates}

echo "[2/5] Installing templates..."
cp -r "$SCRIPT_DIR/vault-template/_templates/"*.md "$VAULT_PATH/DX-Memory/_templates/" 2>/dev/null || true

echo "[3/5] Making scripts executable..."
chmod +x "$SCRIPT_DIR/dx-sync"
chmod +x "$SCRIPT_DIR/hooks/"*.sh
chmod +x "$SCRIPT_DIR/scripts/"*.py

echo "[4/5] Setting environment..."
export OBSIDIAN_VAULT_PATH="$VAULT_PATH"

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$rc" ] && ! grep -q "OBSIDIAN_VAULT_PATH" "$rc" 2>/dev/null; then
        {
            echo ""
            echo "# DX Vault Sync"
            echo "export OBSIDIAN_VAULT_PATH=\"$VAULT_PATH\""
            echo "export PATH=\"\$PATH:$SCRIPT_DIR\""
        } >> "$rc"
        echo "  Updated $rc"
    fi
done

echo "[5/5] Running tests..."
python3 "$SCRIPT_DIR/tests/test_sync.py" && echo "" || echo "Some tests failed — check output above"

echo ""
echo "Setup complete!"
echo ""
echo "Quick start:"
echo "  export PATH=\"\$PATH:$SCRIPT_DIR\""
echo "  dx-sync demo          # Run demo"
echo "  dx-sync sync \"text\"   # Sync text"
echo "  dx-sync status        # Check status"
echo ""
echo "For Claude Code integration, see: $SCRIPT_DIR/claude-code-settings.json"

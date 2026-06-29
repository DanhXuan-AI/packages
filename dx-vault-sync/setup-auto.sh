#!/usr/bin/env bash
# DX Vault Sync — Full Autonomy Setup
# Installs hooks, CLAUDE.md context, cron schedule, and API autostart.
# Run once to enable fully autonomous operation across all projects.
#
# Usage: ./setup-auto.sh [--global] [--vault PATH] [--api-port PORT]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

GLOBAL=false
VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/ObsidianVault}"
API_PORT="8900"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --global) GLOBAL=true; shift ;;
        --vault) VAULT_PATH="$2"; shift 2 ;;
        --api-port) API_PORT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo -e "${PURPLE}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║   DX Vault Sync — Auto Setup         ║"
echo "  ║   Full Loop Autonomy Installer        ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# --- Step 1: Vault directories ---
echo -e "${BLUE}[1/7] Creating vault directories...${NC}"
mkdir -p "$VAULT_PATH/DX-Memory"/{conversations,decisions,entities,learnings,tasks,context,_index,_templates}
mkdir -p "$VAULT_PATH/DX-Memory/business"/{market-intel,marketing-analytics,finance-snapshots,alerts,competitors,reports,_snapshots}
echo -e "${GREEN}  ✓ Vault ready at $VAULT_PATH${NC}"

# --- Step 2: Make hooks executable ---
echo -e "${BLUE}[2/7] Preparing hooks...${NC}"
chmod +x "$SCRIPT_DIR"/hooks/*.sh
echo -e "${GREEN}  ✓ Hooks executable${NC}"

# --- Step 3: Install Claude Code hooks ---
echo -e "${BLUE}[3/7] Installing Claude Code hooks...${NC}"

HOOKS_JSON=$(cat <<ENDJSON
{
  "\$schema": "https://raw.githubusercontent.com/anthropics/claude-code/main/settings.schema.json",
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "${SCRIPT_DIR}/hooks/on_message.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "${SCRIPT_DIR}/hooks/post_conversation.sh"
          }
        ]
      }
    ]
  },
  "env": {
    "OBSIDIAN_VAULT_PATH": "${VAULT_PATH}",
    "DX_LEARN_INTERVAL": "6"
  }
}
ENDJSON
)

if [ "$GLOBAL" = true ]; then
    SETTINGS_FILE="$HOME/.claude/settings.json"
    mkdir -p "$HOME/.claude"
else
    PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    SETTINGS_FILE="$PROJECT_DIR/.claude/settings.json"
    mkdir -p "$PROJECT_DIR/.claude"
fi

if [ -f "$SETTINGS_FILE" ]; then
    BACKUP="${SETTINGS_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$SETTINGS_FILE" "$BACKUP"
    echo -e "${YELLOW}  Backed up existing settings to $BACKUP${NC}"

    python3 -c "
import json, sys
existing = json.loads(open('$SETTINGS_FILE').read())
new_hooks = json.loads('''$HOOKS_JSON''')

if 'hooks' not in existing:
    existing['hooks'] = {}
for event, rules in new_hooks['hooks'].items():
    if event not in existing['hooks']:
        existing['hooks'][event] = []
    existing_cmds = {h.get('hooks', [{}])[0].get('command', '') for h in existing['hooks'][event]}
    for rule in rules:
        cmd = rule.get('hooks', [{}])[0].get('command', '')
        if cmd not in existing_cmds:
            existing['hooks'][event].append(rule)

if 'env' not in existing:
    existing['env'] = {}
existing['env'].update(new_hooks.get('env', {}))

json.dump(existing, open('$SETTINGS_FILE', 'w'), indent=2, ensure_ascii=False)
print('  Merged into existing settings')
" 2>/dev/null && echo -e "${GREEN}  ✓ Hooks merged into $SETTINGS_FILE${NC}" || {
    echo "$HOOKS_JSON" > "$SETTINGS_FILE"
    echo -e "${GREEN}  ✓ Hooks installed at $SETTINGS_FILE${NC}"
}
else
    echo "$HOOKS_JSON" > "$SETTINGS_FILE"
    echo -e "${GREEN}  ✓ Hooks installed at $SETTINGS_FILE${NC}"
fi

# --- Step 4: Environment variables ---
echo -e "${BLUE}[4/7] Setting environment variables...${NC}"

ENV_LINES=$(cat <<'ENVEOF'
# DX Vault Sync — Auto-sync environment
export OBSIDIAN_VAULT_PATH="__VAULT_PATH__"
export DX_LEARN_INTERVAL="6"
ENVEOF
)
ENV_LINES="${ENV_LINES//__VAULT_PATH__/$VAULT_PATH}"

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$rc" ] && ! grep -q "DX Vault Sync" "$rc"; then
        echo "" >> "$rc"
        echo "$ENV_LINES" >> "$rc"
        echo -e "${GREEN}  ✓ Added to $rc${NC}"
    elif [ -f "$rc" ]; then
        echo -e "${YELLOW}  Already in $rc${NC}"
    fi
done

# --- Step 5: CLAUDE.md context ---
echo -e "${BLUE}[5/7] Generating CLAUDE.md context...${NC}"

python3 "$SCRIPT_DIR/scripts/memo_bridge.py" --vault "$VAULT_PATH" inject > "$SCRIPT_DIR/../.vault_context.md" 2>/dev/null || true
echo -e "${GREEN}  ✓ Context cache generated${NC}"

# --- Step 6: Cron schedule for auto-loop ---
echo -e "${BLUE}[6/7] Setting up daily auto-loop...${NC}"

CRON_CMD="0 8 * * * cd $SCRIPT_DIR && python3 scripts/memo_bridge.py --vault $VAULT_PATH tick >> logs/cron_\$(date +\\%Y\\%m\\%d).log 2>&1"
CRON_DIGEST="0 9 * * 1 cd $SCRIPT_DIR && python3 scripts/weekly_digest.py --vault $VAULT_PATH generate >> logs/digest_\$(date +\\%Y\\%m\\%d).log 2>&1"

if command -v crontab &>/dev/null; then
    EXISTING_CRON=$(crontab -l 2>/dev/null || true)
    if echo "$EXISTING_CRON" | grep -q "memo_bridge.py"; then
        echo -e "${YELLOW}  Cron already configured${NC}"
    else
        (echo "$EXISTING_CRON"; echo ""; echo "# DX Vault Sync — Auto-loop"; echo "$CRON_CMD"; echo "$CRON_DIGEST") | crontab -
        echo -e "${GREEN}  ✓ Cron installed: daily tick @ 8AM, weekly digest @ Monday 9AM${NC}"
    fi
else
    echo -e "${YELLOW}  crontab not available — manual scheduling needed${NC}"
    echo -e "  Add to your scheduler:"
    echo -e "  Daily 8AM: ${CYAN}$CRON_CMD${NC}"
    echo -e "  Monday 9AM: ${CYAN}$CRON_DIGEST${NC}"
fi

# --- Step 7: API server autostart ---
echo -e "${BLUE}[7/7] API server setup...${NC}"

SYSTEMD_DIR="$HOME/.config/systemd/user"
if [ -d "/run/systemd" ] && command -v systemctl &>/dev/null; then
    mkdir -p "$SYSTEMD_DIR"
    cat > "$SYSTEMD_DIR/dx-vault-api.service" <<SERVICEEOF
[Unit]
Description=DX Vault Sync API Server
After=network.target

[Service]
Type=simple
Environment=OBSIDIAN_VAULT_PATH=$VAULT_PATH
Environment=DX_VAULT_API_PORT=$API_PORT
WorkingDirectory=$SCRIPT_DIR
ExecStart=$(which python3) $SCRIPT_DIR/api/server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
SERVICEEOF

    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable dx-vault-api.service 2>/dev/null || true
    systemctl --user start dx-vault-api.service 2>/dev/null || true
    echo -e "${GREEN}  ✓ API server systemd service installed (port $API_PORT)${NC}"
else
    echo -e "${YELLOW}  systemd not available — start manually:${NC}"
    echo -e "  ${CYAN}OBSIDIAN_VAULT_PATH=$VAULT_PATH python3 $SCRIPT_DIR/api/server.py &${NC}"
fi

# --- Summary ---
echo ""
echo -e "${PURPLE}════════════════════════════════════════${NC}"
echo -e "${GREEN}Setup complete! System is now autonomous:${NC}"
echo ""
echo -e "  ${CYAN}Vault:${NC}     $VAULT_PATH"
echo -e "  ${CYAN}Hooks:${NC}     $SETTINGS_FILE"
echo -e "  ${CYAN}Auto-learn:${NC} Every 6 messages"
echo -e "  ${CYAN}Auto-sync:${NC}  On conversation end"
echo -e "  ${CYAN}Gap scan:${NC}   Daily at 8AM"
echo -e "  ${CYAN}Digest:${NC}    Weekly Monday 9AM"
echo -e "  ${CYAN}API:${NC}       port $API_PORT"
echo ""
echo -e "${CYAN}Verify:${NC} $SCRIPT_DIR/dx-sync memo"
echo -e "${CYAN}Test:${NC}   $SCRIPT_DIR/dx-sync gap-report"
echo -e "${PURPLE}════════════════════════════════════════${NC}"

# DX Advisory — Project Context

## DX Vault Sync (Second Brain Auto-Sync)

This repo contains the DX Vault Sync system — a 4-phase autonomous knowledge loop:

- **Phase 1**: Claude ↔ Obsidian Vault auto-sync (NLP extraction, YAML frontmatter)
- **Phase 2**: Business Data Loop (Bigdata.com + Supermetrics MCP)
- **Phase 3**: ChatGPT Bridge (FastAPI REST API, port 8900)
- **Phase 4**: Full Loop Autonomy (gap detection, auto-research, weekly digest, memo bridge)

## Quick Commands

```bash
dx-vault-sync/dx-sync status        # Vault stats
dx-vault-sync/dx-sync memo          # Full memory status
dx-vault-sync/dx-sync gap-report    # Knowledge gap analysis
dx-vault-sync/dx-sync digest        # Weekly digest
dx-vault-sync/dx-sync memo-tick     # Run auto-loop (gaps + research + context refresh)
dx-vault-sync/dx-sync research prompt  # Auto-research prompts
```

## Auto-Sync Hooks

Hooks are configured in `.claude/settings.json`:
- **Notification**: Every 6 messages, extracts insights and syncs to vault
- **Stop**: On conversation end, syncs full transcript + runs memo tick

## Vault Location

Obsidian Vault: `$OBSIDIAN_VAULT_PATH` (default: `/home/user/ObsidianVault`)
Memory directory: `DX-Memory/`

## Testing

```bash
cd dx-vault-sync && python3 tests/test_sync.py && python3 tests/test_business.py && python3 tests/test_api.py && python3 tests/test_phase4.py
```

95 tests across 4 phases.

## Language

User communicates in Vietnamese. System outputs in Vietnamese where appropriate.
Technical terms in English.

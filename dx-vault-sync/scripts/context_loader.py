#!/usr/bin/env python3
"""
DX Vault Sync — Context Loader
Loads relevant context from Obsidian Vault before Claude Code conversations.
Generates a context summary that can be injected into CLAUDE.md or session context.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from vault_writer import VaultWriter


class ContextLoader:
    def __init__(self, vault_path: str, memory_dir: str = "DX-Memory"):
        self.writer = VaultWriter(vault_path, memory_dir)
        self.vault_path = Path(vault_path).expanduser()
        self.memory_path = self.vault_path / memory_dir

    def load_recent_context(self, hours: int = 24, limit: int = 10) -> str:
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = []

        for note in self.writer.read_context(limit=50):
            created = note.get("created", "")
            if created:
                try:
                    note_time = datetime.fromisoformat(created)
                    if note_time >= cutoff:
                        recent.append(note)
                except ValueError:
                    continue

        recent = recent[:limit]
        return self._format_context(recent, f"Context from last {hours}h")

    def load_category_context(self, category: str, limit: int = 10) -> str:
        notes = self.writer.read_context(category=category, limit=limit)
        label_map = {
            "decision": "Quyết định gần đây",
            "learning": "Kiến thức đã học",
            "entity": "Thực thể liên quan",
            "task": "Công việc đang mở",
            "context": "Ngữ cảnh cá nhân",
            "conversation": "Hội thoại gần đây",
        }
        return self._format_context(notes, label_map.get(category, category))

    def load_relevant_context(self, query: str, limit: int = 5) -> str:
        results = self.writer.search_vault(query, limit=limit)
        return self._format_context(results, f"Context for: {query}")

    def generate_claude_context(self) -> str:
        parts = [
            "# DX Vault — Active Context",
            f"*Last loaded: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            "",
        ]

        open_tasks = self._get_open_tasks()
        if open_tasks:
            parts.append("## Open Tasks")
            for task in open_tasks[:5]:
                title = task.get("frontmatter", {}).get("title", task.get("filename", ""))
                parts.append(f"- [ ] {title}")
            parts.append("")

        recent_decisions = self.writer.read_context(category="decision", limit=3)
        if recent_decisions:
            parts.append("## Recent Decisions")
            for dec in recent_decisions:
                title = dec.get("frontmatter", {}).get("title", dec.get("filename", ""))
                parts.append(f"- {title}")
            parts.append("")

        preferences = self.writer.read_context(category="context", limit=5)
        if preferences:
            parts.append("## User Preferences")
            for pref in preferences:
                content = pref.get("content", "").split("\n")[0][:100]
                if content:
                    parts.append(f"- {content}")
            parts.append("")

        stats = self.writer.get_stats()
        parts.append("## Vault Stats")
        parts.append(f"- Total notes: {stats['total_notes']}")
        for cat, count in stats.get("categories", {}).items():
            if count > 0:
                parts.append(f"- {cat}: {count}")
        if stats.get("last_sync"):
            parts.append(f"- Last sync: {stats['last_sync']}")

        return "\n".join(parts)

    def export_for_session(self, output_path: Optional[str] = None) -> str:
        context = self.generate_claude_context()

        if output_path:
            Path(output_path).write_text(context, encoding="utf-8")

        return context

    def _get_open_tasks(self) -> list[dict]:
        tasks = self.writer.read_context(category="task", limit=20)
        return [
            t
            for t in tasks
            if t.get("frontmatter", {}).get("status") in ("open", "in-progress", None)
        ]

    def _format_context(self, notes: list[dict], header: str) -> str:
        if not notes:
            return f"## {header}\nKhông có dữ liệu.\n"

        parts = [f"## {header}", ""]
        for note in notes:
            fm = note.get("frontmatter", {})
            title = fm.get("title", note.get("filename", "untitled"))
            category = fm.get("type", "unknown")
            tags = ", ".join(fm.get("tags", []))
            content_preview = note.get("content", "")[:200]

            parts.append(f"### {title}")
            parts.append(f"*Category: {category} | Tags: {tags}*")
            parts.append(content_preview)
            parts.append("")

        return "\n".join(parts)


if __name__ == "__main__":
    import sys

    vault_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dx-vault-demo"
    loader = ContextLoader(vault_path)

    print("=== Claude Context ===")
    print(loader.generate_claude_context())

    if len(sys.argv) > 2:
        query = sys.argv[2]
        print(f"\n=== Search: {query} ===")
        print(loader.load_relevant_context(query))

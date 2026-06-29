#!/usr/bin/env python3
"""
DX Vault Sync — Obsidian Vault Writer
Writes extracted insights as Obsidian-compatible markdown files
with YAML frontmatter and wiki links.
"""

import os
import re
import json
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional


CATEGORY_DIRS = {
    "decision": "decisions",
    "learning": "learnings",
    "entity": "entities",
    "task": "tasks",
    "context": "context",
    "conversation": "conversations",
}

CATEGORY_ICONS = {
    "decision": "🎯",
    "learning": "💡",
    "entity": "👤",
    "task": "✅",
    "context": "🧠",
    "conversation": "💬",
}

STATUS_MAP = {
    "task": "open",
    "decision": "active",
    "learning": "captured",
    "entity": "active",
    "context": "current",
    "conversation": "logged",
}


class VaultWriter:
    def __init__(self, vault_path: str, memory_dir: str = "DX-Memory"):
        self.vault_path = Path(vault_path).expanduser()
        self.memory_dir = memory_dir
        self.memory_path = self.vault_path / memory_dir
        self._ensure_dirs()

    def _ensure_dirs(self):
        for subdir in CATEGORY_DIRS.values():
            (self.memory_path / subdir).mkdir(parents=True, exist_ok=True)
        (self.memory_path / "_index").mkdir(parents=True, exist_ok=True)

    def write_insight(self, insight: dict) -> Path:
        category = insight.get("category", "learning")
        subdir = CATEGORY_DIRS.get(category, "learnings")
        filename = self._sanitize_filename(insight.get("title", "untitled"))
        filepath = self.memory_path / subdir / f"{filename}.md"

        if filepath.exists():
            filepath = self._handle_duplicate(filepath, insight)

        content = self._build_markdown(insight)
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def write_batch(self, insights: list[dict]) -> list[Path]:
        written = []
        for insight in insights:
            try:
                path = self.write_insight(insight)
                written.append(path)
            except (OSError, ValueError) as e:
                print(f"Error writing insight: {e}")
        self._update_index(insights)
        return written

    def write_conversation_log(self, summary: dict) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        title = summary.get("title", f"Session {timestamp}")
        filename = self._sanitize_filename(f"{timestamp}_{title}")
        filepath = self.memory_path / "conversations" / f"{filename}.md"

        frontmatter = {
            "type": "conversation",
            "created": datetime.now().isoformat(),
            "topics": summary.get("topics", []),
            "tags": summary.get("tags", ["conversation"]),
            "message_count": summary.get("message_count", 0),
            "status": "logged",
            "auto_synced": True,
        }

        content_parts = [
            "---",
            yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip(),
            "---",
            "",
            f"# {title}",
            "",
            summary.get("content", ""),
            "",
            "---",
            f"*Auto-synced by DX Vault Sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ]

        filepath.write_text("\n".join(content_parts), encoding="utf-8")
        return filepath

    def read_context(self, category: Optional[str] = None, limit: int = 10) -> list[dict]:
        results = []
        search_dirs = (
            [self.memory_path / CATEGORY_DIRS[category]]
            if category and category in CATEGORY_DIRS
            else [self.memory_path / d for d in CATEGORY_DIRS.values()]
        )

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for md_file in sorted(search_dir.glob("*.md"), key=os.path.getmtime, reverse=True):
                try:
                    parsed = self._parse_vault_note(md_file)
                    if parsed:
                        results.append(parsed)
                except (OSError, ValueError):
                    continue

        results.sort(key=lambda x: x.get("created", ""), reverse=True)
        return results[:limit]

    def search_vault(self, query: str, limit: int = 10) -> list[dict]:
        query_lower = query.lower()
        results = []

        for subdir in CATEGORY_DIRS.values():
            dir_path = self.memory_path / subdir
            if not dir_path.exists():
                continue
            for md_file in dir_path.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8").lower()
                    if query_lower in content:
                        parsed = self._parse_vault_note(md_file)
                        if parsed:
                            score = content.count(query_lower)
                            parsed["relevance_score"] = score
                            results.append(parsed)
                except (OSError, ValueError):
                    continue

        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return results[:limit]

    def get_stats(self) -> dict:
        stats = {"total_notes": 0, "categories": {}, "last_sync": None}

        for category, subdir in CATEGORY_DIRS.items():
            dir_path = self.memory_path / subdir
            if dir_path.exists():
                count = len(list(dir_path.glob("*.md")))
                stats["categories"][category] = count
                stats["total_notes"] += count

        index_file = self.memory_path / "_index" / "sync_log.json"
        if index_file.exists():
            try:
                log = json.loads(index_file.read_text(encoding="utf-8"))
                stats["last_sync"] = log.get("last_sync")
            except (json.JSONDecodeError, OSError):
                pass

        return stats

    def _build_markdown(self, insight: dict) -> str:
        category = insight.get("category", "learning")

        frontmatter = {
            "type": category,
            "created": insight.get("timestamp", datetime.now().isoformat()),
            "tags": insight.get("tags", [category]),
            "source": insight.get("source", "unknown"),
            "confidence": insight.get("confidence", 0.5),
            "status": STATUS_MAP.get(category, "active"),
            "auto_synced": True,
            "id": insight.get("id", ""),
        }

        links = insight.get("links", [])
        if links:
            frontmatter["links"] = links

        title = insight.get("title", "Untitled")
        icon = CATEGORY_ICONS.get(category, "📝")
        content = insight.get("content", "")

        link_section = ""
        if links:
            link_items = " | ".join(f"[[{link}]]" for link in links)
            link_section = f"\n## Liên kết\n{link_items}\n"

        parts = [
            "---",
            yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip(),
            "---",
            "",
            f"# {icon} {title}",
            "",
            content,
            "",
            link_section,
            "---",
            f"*Auto-synced by DX Vault Sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ]

        return "\n".join(parts)

    def _sanitize_filename(self, name: str) -> str:
        sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
        sanitized = re.sub(r"\s+", "_", sanitized)
        sanitized = sanitized.strip("_.")
        return sanitized[:100] if sanitized else "untitled"

    def _handle_duplicate(self, filepath: Path, insight: dict) -> Path:
        stem = filepath.stem
        suffix = filepath.suffix
        parent = filepath.parent
        counter = 1
        while filepath.exists():
            filepath = parent / f"{stem}_{counter}{suffix}"
            counter += 1
        return filepath

    def _parse_vault_note(self, filepath: Path) -> Optional[dict]:
        text = filepath.read_text(encoding="utf-8")
        frontmatter = {}
        content = text

        fm_match = re.match(r"^---\s*\n(.+?)\n---\s*\n(.*)$", text, re.DOTALL)
        if fm_match:
            try:
                frontmatter = yaml.safe_load(fm_match.group(1)) or {}
            except yaml.YAMLError:
                pass
            content = fm_match.group(2)

        return {
            "path": str(filepath),
            "filename": filepath.stem,
            "frontmatter": frontmatter,
            "content": content.strip(),
            "created": frontmatter.get("created", ""),
            "category": frontmatter.get("type", "unknown"),
            "tags": frontmatter.get("tags", []),
        }

    def _update_index(self, insights: list[dict]):
        index_file = self.memory_path / "_index" / "sync_log.json"
        log = {"syncs": []}

        if index_file.exists():
            try:
                log = json.loads(index_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        log["last_sync"] = datetime.now().isoformat()
        log["syncs"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "count": len(insights),
                "categories": list({i.get("category", "") for i in insights}),
            }
        )

        log["syncs"] = log["syncs"][-100:]
        index_file.write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    import sys

    vault_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dx-vault-demo"
    writer = VaultWriter(vault_path)

    demo_insights = [
        {
            "id": "demo001",
            "category": "decision",
            "title": "Chọn FastAPI cho backend POScake v2",
            "content": "Quyết định sử dụng FastAPI thay vì Flask cho backend POScake v2.\n\nLý do:\n- Hiệu năng async tốt hơn\n- Auto-generate OpenAPI docs\n- Type hints native",
            "tags": ["decision", "python", "api", "poscake"],
            "links": ["POScake", "FastAPI"],
            "source": "claude-code:demo",
            "timestamp": datetime.now().isoformat(),
            "confidence": 0.9,
        },
        {
            "id": "demo002",
            "category": "task",
            "title": "Setup CI/CD cho DX packages repo",
            "content": "Cần thiết lập GitHub Actions cho auto-update packages:\n- Kiểm tra upstream releases hàng tuần\n- Auto download và commit\n- Notify qua Slack",
            "tags": ["task", "devops", "automation"],
            "links": ["DX Packages", "GitHub Actions"],
            "source": "claude-code:demo",
            "timestamp": datetime.now().isoformat(),
            "confidence": 0.85,
        },
    ]

    paths = writer.write_batch(demo_insights)
    for p in paths:
        print(f"Written: {p}")

    stats = writer.get_stats()
    print(f"\nVault stats: {json.dumps(stats, ensure_ascii=False, indent=2)}")

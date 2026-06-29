#!/usr/bin/env python3
"""
DX Vault Sync — Phase 4: Memo Bridge
Integrates the vault memory system with Claude Code's CLAUDE.md,
Jarvis OS long-term memory, and session context injection.

This is the unification layer — reads from all sources, writes to vault,
and generates context that all platforms can consume.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from vault_writer import VaultWriter
from context_loader import ContextLoader
from gap_detector import GapDetector
from auto_research import AutoResearch
from weekly_digest import WeeklyDigest


class MemoBridge:
    def __init__(self, vault_path: str, memory_dir: str = "DX-Memory"):
        self.vault_path = Path(vault_path).expanduser()
        self.memory_path = self.vault_path / memory_dir
        self.writer = VaultWriter(str(self.vault_path), memory_dir)
        self.loader = ContextLoader(str(self.vault_path), memory_dir)
        self.detector = GapDetector(str(self.vault_path), memory_dir)
        self.researcher = AutoResearch(str(self.vault_path), memory_dir)
        self.digest = WeeklyDigest(str(self.vault_path), memory_dir)

    def generate_claude_md(self, output_path: Optional[str] = None) -> str:
        context = self.loader.generate_claude_context()
        scan = self.detector.scan_and_score()
        prompts = self.detector.get_research_prompts(3)

        parts = [context, ""]

        parts.append("## Vault Health")
        parts.append(f"- Health score: {scan['health_score']}/100")
        gap_count = sum(len(v) if isinstance(v, list) else 0 for v in scan["gaps"].values())
        parts.append(f"- Knowledge gaps: {gap_count}")
        parts.append("")

        if prompts:
            parts.append("## Auto-Research Queue")
            for p in prompts:
                parts.append(f"- [{p.get('priority', 'medium')}] {p.get('prompt', '')[:80]}")
            parts.append("")

        if scan.get("recommendations"):
            parts.append("## Recommended Actions")
            for rec in scan["recommendations"][:3]:
                parts.append(f"- {rec}")
            parts.append("")

        result = "\n".join(parts)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(result, encoding="utf-8")

        return result

    def inject_session_context(self, session_dir: Optional[str] = None) -> str:
        parts = [
            "# DX Vault — Session Context",
            f"*Injected: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            "",
        ]

        open_tasks = self.loader._get_open_tasks()
        if open_tasks:
            parts.append("## Công việc đang mở")
            for task in open_tasks[:5]:
                title = task.get("frontmatter", {}).get("title", task.get("filename", ""))
                parts.append(f"- [ ] {title}")
            parts.append("")

        recent = self.writer.read_context(limit=5)
        if recent:
            parts.append("## Hoạt động gần đây")
            for note in recent:
                fm = note.get("frontmatter", {})
                title = fm.get("title", note.get("filename", ""))
                cat = fm.get("type", "")
                parts.append(f"- [{cat}] {title}")
            parts.append("")

        scan = self.detector.scan_and_score()
        if scan["health_score"] < 70:
            parts.append("## ⚠️ Vault cần chú ý")
            parts.append(f"Health score: {scan['health_score']}/100")
            for rec in scan.get("recommendations", [])[:2]:
                parts.append(f"- {rec}")
            parts.append("")

        return "\n".join(parts)

    def auto_loop_tick(self) -> dict:
        result = {
            "timestamp": datetime.now().isoformat(),
            "actions": [],
        }

        scan = self.detector.scan_and_score()
        result["health_score"] = scan["health_score"]

        stale_data = [f for f in scan["gaps"].get("data_freshness", []) if not f.get("fresh")]
        if stale_data:
            prompts = self.detector.get_research_prompts(3)
            result["research_prompts"] = prompts
            result["actions"].append(f"Generated {len(prompts)} research prompts for stale data")

        now = datetime.now()
        if now.weekday() == 0 and now.hour < 12:
            digest_result = self.digest.generate(days=7, save=True)
            result["weekly_digest"] = {
                "period": digest_result["period"],
                "notes_count": digest_result["summary"]["new_notes"],
                "saved_path": digest_result.get("saved_path", ""),
            }
            result["actions"].append("Generated weekly digest (Monday auto-trigger)")

        claude_md = self.generate_claude_md()
        cache_path = self.memory_path / "_index" / "claude_context.md"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(claude_md, encoding="utf-8")
        result["actions"].append("Updated CLAUDE.md context cache")

        return result

    def sync_from_claude_md(self, claude_md_path: str) -> dict:
        path = Path(claude_md_path).expanduser()
        if not path.exists():
            return {"error": f"CLAUDE.md not found: {claude_md_path}"}

        content = path.read_text(encoding="utf-8")
        from extract_insights import InsightExtractor
        extractor = InsightExtractor()
        insights = extractor.extract_from_text(content, source="claude-md")

        if insights:
            paths = self.writer.write_batch(insights)
            return {
                "source": str(path),
                "insights_found": len(insights),
                "files_written": len(paths),
            }

        return {"source": str(path), "insights_found": 0, "files_written": 0}

    def export_for_jarvis(self) -> dict:
        context = self.loader.generate_claude_context()
        stats = self.writer.get_stats()
        open_tasks = self.loader._get_open_tasks()
        recent_decisions = self.writer.read_context(category="decision", limit=5)

        return {
            "platform": "jarvis",
            "exported_at": datetime.now().isoformat(),
            "context_summary": context,
            "stats": stats,
            "open_tasks": [
                {
                    "title": t.get("frontmatter", {}).get("title", t.get("filename", "")),
                    "status": t.get("frontmatter", {}).get("status", "open"),
                    "created": t.get("created", ""),
                }
                for t in open_tasks
            ],
            "recent_decisions": [
                {
                    "title": d.get("frontmatter", {}).get("title", d.get("filename", "")),
                    "created": d.get("created", ""),
                }
                for d in recent_decisions
            ],
        }

    def get_full_status(self) -> dict:
        stats = self.writer.get_stats()
        scan = self.detector.scan_and_score()
        research_history = self.researcher.get_research_history(5)

        return {
            "vault_path": str(self.vault_path),
            "stats": stats,
            "health_score": scan["health_score"],
            "gap_summary": {
                "stale_notes": len(scan["gaps"].get("stale_notes", [])),
                "orphan_notes": len(scan["gaps"].get("orphan_notes", [])),
                "broken_links": len(scan["gaps"].get("broken_links", [])),
                "empty_categories": len(scan["gaps"].get("empty_categories", [])),
                "open_tasks": len(scan["gaps"].get("open_tasks", [])),
                "topic_gaps": len(scan["gaps"].get("topic_gaps", [])),
            },
            "data_freshness": scan["gaps"].get("data_freshness", []),
            "recent_research": research_history,
            "recommendations": scan.get("recommendations", []),
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DX Vault — Memo Bridge")
    parser.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT_PATH", "/tmp/dx-vault-demo"))
    parser.add_argument("--memory-dir", default="DX-Memory")
    parser.add_argument("command", nargs="?", default="status",
                        choices=["status", "claude-md", "inject", "tick", "sync-claude", "export-jarvis"])
    parser.add_argument("--output", default="")
    parser.add_argument("--claude-md-path", default="")

    args = parser.parse_args()
    bridge = MemoBridge(args.vault, args.memory_dir)

    if args.command == "status":
        result = bridge.get_full_status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "claude-md":
        md = bridge.generate_claude_md(args.output or None)
        if not args.output:
            print(md)
    elif args.command == "inject":
        print(bridge.inject_session_context())
    elif args.command == "tick":
        result = bridge.auto_loop_tick()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "sync-claude":
        path = args.claude_md_path or os.path.expanduser("~/.claude/CLAUDE.md")
        result = bridge.sync_from_claude_md(path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "export-jarvis":
        result = bridge.export_for_jarvis()
        print(json.dumps(result, ensure_ascii=False, indent=2))

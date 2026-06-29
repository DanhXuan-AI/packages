#!/usr/bin/env python3
"""
DX Vault Sync — Phase 4: Weekly Digest Generator
Auto-compiles weekly summary of all vault activity — new notes, decisions,
tasks completed, business metrics changes, and knowledge growth.
"""

import json
import os
import re
import sys
import yaml
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from vault_writer import VaultWriter, CATEGORY_DIRS
from gap_detector import GapDetector

BUSINESS_DIRS = {
    "market-intel": "business/market-intel",
    "marketing-analytics": "business/marketing-analytics",
    "finance-snapshots": "business/finance-snapshots",
    "alerts": "business/alerts",
    "competitors": "business/competitors",
    "reports": "business/reports",
}


class WeeklyDigest:
    def __init__(self, vault_path: str, memory_dir: str = "DX-Memory"):
        self.vault_path = Path(vault_path).expanduser()
        self.memory_path = self.vault_path / memory_dir
        self.writer = VaultWriter(str(self.vault_path), memory_dir)
        self.detector = GapDetector(str(self.vault_path), memory_dir)
        self.digest_path = self.memory_path / "business" / "reports"

    def generate(self, days: int = 7, save: bool = True) -> dict:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        notes = self._get_notes_in_range(start_date, end_date)

        digest = {
            "period": {
                "start": start_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d"),
                "days": days,
            },
            "summary": self._build_summary(notes),
            "categories": self._categorize_notes(notes),
            "decisions": self._extract_decisions(notes),
            "tasks": self._task_summary(notes, start_date),
            "learnings": self._extract_learnings(notes),
            "business": self._business_summary(start_date, end_date),
            "health": self.detector.scan_and_score(),
            "generated_at": end_date.isoformat(),
        }

        if save:
            digest["saved_path"] = str(self._save_digest(digest))

        return digest

    def generate_markdown(self, days: int = 7) -> str:
        digest = self.generate(days=days, save=False)
        period = digest["period"]

        parts = [
            f"# 📋 Weekly Digest: {period['start']} → {period['end']}",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            "",
        ]

        summary = digest["summary"]
        parts.extend([
            "## 📊 Tổng quan",
            f"- Notes mới: **{summary['new_notes']}**",
            f"- Categories active: **{summary['active_categories']}**",
            f"- Vault health: **{digest['health']['health_score']}/100**",
            "",
        ])

        cats = digest["categories"]
        if cats:
            parts.append("### Notes theo category")
            for cat, count in sorted(cats.items(), key=lambda x: x[1], reverse=True):
                parts.append(f"- {cat}: {count}")
            parts.append("")

        decisions = digest["decisions"]
        if decisions:
            parts.append(f"## 🎯 Quyết định ({len(decisions)})")
            for dec in decisions:
                parts.append(f"- **{dec['title']}**")
                if dec.get("preview"):
                    parts.append(f"  {dec['preview']}")
            parts.append("")

        tasks = digest["tasks"]
        if tasks.get("completed"):
            parts.append(f"## ✅ Tasks hoàn thành ({len(tasks['completed'])})")
            for t in tasks["completed"]:
                parts.append(f"- ~~{t['title']}~~")
            parts.append("")

        if tasks.get("opened"):
            parts.append(f"## 📝 Tasks mới ({len(tasks['opened'])})")
            for t in tasks["opened"]:
                parts.append(f"- [ ] {t['title']}")
            parts.append("")

        if tasks.get("still_open"):
            parts.append(f"## ⏳ Tasks đang mở ({len(tasks['still_open'])})")
            for t in tasks["still_open"]:
                days_open = t.get("days_open", 0)
                age = f" ({days_open}d)" if days_open > 0 else ""
                parts.append(f"- [ ] {t['title']}{age}")
            parts.append("")

        learnings = digest["learnings"]
        if learnings:
            parts.append(f"## 💡 Kiến thức mới ({len(learnings)})")
            for l in learnings:
                parts.append(f"- {l['title']}")
            parts.append("")

        biz = digest["business"]
        if biz.get("has_data"):
            parts.append("## 📈 Business Data")

            if biz.get("finance"):
                fin = biz["finance"]
                parts.append("### Tài chính")
                if fin.get("latest_revenue"):
                    parts.append(f"- Revenue: {self._format_number(fin['latest_revenue'])}")
                if fin.get("latest_profit"):
                    parts.append(f"- Profit: {self._format_number(fin['latest_profit'])}")
                if fin.get("snapshots_count"):
                    parts.append(f"- Snapshots tuần này: {fin['snapshots_count']}")
                parts.append("")

            if biz.get("marketing"):
                mkt = biz["marketing"]
                parts.append("### Marketing")
                if mkt.get("reports_count"):
                    parts.append(f"- Reports tuần này: {mkt['reports_count']}")
                parts.append("")

            if biz.get("alerts"):
                parts.append(f"### Cảnh báo ({len(biz['alerts'])})")
                for alert in biz["alerts"][:5]:
                    parts.append(f"- ⚠️ {alert}")
                parts.append("")

        health = digest["health"]
        if health.get("recommendations"):
            parts.append("## 💡 Recommendations")
            for rec in health["recommendations"]:
                parts.append(f"- {rec}")
            parts.append("")

        parts.extend([
            "---",
            "*Auto-generated by DX Vault Sync — Weekly Digest Engine*",
        ])

        return "\n".join(parts)

    def _get_notes_in_range(self, start: datetime, end: datetime) -> list[dict]:
        notes = []
        all_dirs = dict(CATEGORY_DIRS)
        for key, subdir in BUSINESS_DIRS.items():
            all_dirs[key] = subdir

        for category, subdir in all_dirs.items():
            dir_path = self.memory_path / subdir
            if not dir_path.exists():
                continue
            for md_file in dir_path.glob("*.md"):
                mtime = datetime.fromtimestamp(os.path.getmtime(md_file))
                if start <= mtime <= end:
                    parsed = self.writer._parse_vault_note(md_file)
                    if parsed:
                        parsed["_category_dir"] = category
                        parsed["_mtime"] = mtime
                        notes.append(parsed)

        notes.sort(key=lambda n: n.get("_mtime", datetime.min), reverse=True)
        return notes

    def _build_summary(self, notes: list[dict]) -> dict:
        categories = {n.get("_category_dir", n.get("category", "unknown")) for n in notes}
        return {
            "new_notes": len(notes),
            "active_categories": len(categories),
        }

    def _categorize_notes(self, notes: list[dict]) -> dict:
        counts = Counter()
        for note in notes:
            cat = note.get("_category_dir", note.get("category", "unknown"))
            counts[cat] += 1
        return dict(counts)

    def _extract_decisions(self, notes: list[dict]) -> list[dict]:
        decisions = []
        for note in notes:
            if note.get("category") == "decision" or note.get("_category_dir") == "decision":
                fm = note.get("frontmatter", {})
                content = note.get("content", "")
                preview = content.split("\n")[0][:120] if content else ""
                decisions.append({
                    "title": fm.get("title", note["filename"]),
                    "preview": preview,
                    "created": note.get("created", ""),
                })
        return decisions

    def _task_summary(self, notes: list[dict], period_start: datetime) -> dict:
        all_tasks = []
        task_dir = self.memory_path / "tasks"
        if task_dir.exists():
            for md_file in task_dir.glob("*.md"):
                parsed = self.writer._parse_vault_note(md_file)
                if parsed:
                    all_tasks.append(parsed)

        now = datetime.now()
        completed = []
        opened = []
        still_open = []

        period_notes = [n for n in notes if n.get("_category_dir") == "task" or n.get("category") == "task"]
        for note in period_notes:
            fm = note.get("frontmatter", {})
            title = fm.get("title", note["filename"])
            status = fm.get("status", "open")

            if status in ("completed", "done", "closed"):
                completed.append({"title": title})
            else:
                opened.append({"title": title})

        for task in all_tasks:
            fm = task.get("frontmatter", {})
            status = fm.get("status", "open")
            if status in ("open", "in-progress", None):
                title = fm.get("title", task["filename"])
                created_str = task.get("created", "")
                days_open = 0
                if created_str:
                    try:
                        created = datetime.fromisoformat(created_str)
                        days_open = (now - created).days
                    except ValueError:
                        pass
                still_open.append({"title": title, "days_open": days_open})

        return {
            "completed": completed,
            "opened": opened,
            "still_open": still_open,
        }

    def _extract_learnings(self, notes: list[dict]) -> list[dict]:
        learnings = []
        for note in notes:
            if note.get("category") == "learning" or note.get("_category_dir") == "learning":
                fm = note.get("frontmatter", {})
                learnings.append({
                    "title": fm.get("title", note["filename"]),
                    "tags": note.get("tags", []),
                })
        return learnings

    def _business_summary(self, start: datetime, end: datetime) -> dict:
        result = {"has_data": False}

        fin_dir = self.memory_path / "business" / "finance-snapshots"
        if fin_dir.exists():
            fin_notes = []
            for md_file in fin_dir.glob("*.md"):
                mtime = datetime.fromtimestamp(os.path.getmtime(md_file))
                if start <= mtime <= end:
                    parsed = self.writer._parse_vault_note(md_file)
                    if parsed:
                        fin_notes.append(parsed)

            if fin_notes:
                result["has_data"] = True
                latest = fin_notes[0]
                fm = latest.get("frontmatter", {})
                result["finance"] = {
                    "snapshots_count": len(fin_notes),
                    "latest_revenue": fm.get("revenue"),
                    "latest_profit": fm.get("profit"),
                    "latest_period": fm.get("period", ""),
                }

        mkt_dir = self.memory_path / "business" / "marketing-analytics"
        if mkt_dir.exists():
            mkt_notes = []
            for md_file in mkt_dir.glob("*.md"):
                mtime = datetime.fromtimestamp(os.path.getmtime(md_file))
                if start <= mtime <= end:
                    mkt_notes.append(md_file)

            if mkt_notes:
                result["has_data"] = True
                result["marketing"] = {"reports_count": len(mkt_notes)}

        alert_dir = self.memory_path / "business" / "alerts"
        if alert_dir.exists():
            alerts = []
            for md_file in alert_dir.glob("*.md"):
                mtime = datetime.fromtimestamp(os.path.getmtime(md_file))
                if start <= mtime <= end:
                    parsed = self.writer._parse_vault_note(md_file)
                    if parsed:
                        content = parsed.get("content", "")
                        first_line = content.split("\n")[0][:100] if content else parsed["filename"]
                        alerts.append(first_line)

            if alerts:
                result["has_data"] = True
                result["alerts"] = alerts

        return result

    def _save_digest(self, digest: dict) -> Path:
        self.digest_path.mkdir(parents=True, exist_ok=True)
        period = digest["period"]
        filename = f"weekly-digest_{period['start']}_{period['end']}"
        filepath = self.digest_path / f"{filename}.md"

        md_content = self.generate_markdown(digest["period"]["days"])

        frontmatter = {
            "type": "weekly-digest",
            "created": datetime.now().isoformat(),
            "period_start": period["start"],
            "period_end": period["end"],
            "tags": ["digest", "weekly", "auto-generated"],
            "notes_count": digest["summary"]["new_notes"],
            "health_score": digest["health"]["health_score"],
            "auto_synced": True,
        }

        content_parts = [
            "---",
            yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip(),
            "---",
            "",
            md_content,
        ]

        filepath.write_text("\n".join(content_parts), encoding="utf-8")
        return filepath

    def _format_number(self, n) -> str:
        if n is None:
            return "N/A"
        try:
            n = float(n)
        except (ValueError, TypeError):
            return str(n)

        if abs(n) >= 1_000_000_000:
            return f"{n / 1_000_000_000:.1f}B"
        elif abs(n) >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        elif abs(n) >= 1_000:
            return f"{n / 1_000:.1f}K"
        return f"{n:.0f}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DX Vault — Weekly Digest Generator")
    parser.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT_PATH", "/tmp/dx-vault-demo"))
    parser.add_argument("--memory-dir", default="DX-Memory")
    parser.add_argument("command", nargs="?", default="generate", choices=["generate", "markdown", "json"])
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--no-save", action="store_true")

    args = parser.parse_args()
    digest = WeeklyDigest(args.vault, args.memory_dir)

    if args.command == "markdown":
        print(digest.generate_markdown(args.days))
    elif args.command == "json":
        result = digest.generate(args.days, save=not args.no_save)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        result = digest.generate(args.days, save=not args.no_save)
        print(digest.generate_markdown(args.days))
        if result.get("saved_path"):
            print(f"\n📁 Saved to: {result['saved_path']}")

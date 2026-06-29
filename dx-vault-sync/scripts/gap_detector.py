#!/usr/bin/env python3
"""
DX Vault Sync — Phase 4: Knowledge Gap Detector
Analyzes vault for missing connections, stale data, uncovered topics,
and orphaned notes. Generates research prompts to fill gaps.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from vault_writer import VaultWriter, CATEGORY_DIRS

BUSINESS_DIRS = {
    "market-intel": "business/market-intel",
    "marketing-analytics": "business/marketing-analytics",
    "finance-snapshots": "business/finance-snapshots",
    "alerts": "business/alerts",
    "competitors": "business/competitors",
    "reports": "business/reports",
}

STALE_THRESHOLDS = {
    "task": 7,
    "decision": 30,
    "entity": 14,
    "learning": 60,
    "context": 30,
    "finance-snapshots": 7,
    "marketing-analytics": 7,
    "market-intel": 14,
}


class GapDetector:
    def __init__(self, vault_path: str, memory_dir: str = "DX-Memory"):
        self.vault_path = Path(vault_path).expanduser()
        self.memory_path = self.vault_path / memory_dir
        self.writer = VaultWriter(str(self.vault_path), memory_dir)

    def full_scan(self) -> dict:
        notes = self._load_all_notes()
        return {
            "timestamp": datetime.now().isoformat(),
            "total_notes": len(notes),
            "gaps": {
                "stale_notes": self._find_stale_notes(notes),
                "orphan_notes": self._find_orphan_notes(notes),
                "empty_categories": self._find_empty_categories(),
                "broken_links": self._find_broken_links(notes),
                "missing_tags": self._find_undertaged_notes(notes),
                "open_tasks": self._find_stale_tasks(notes),
                "topic_gaps": self._find_topic_gaps(notes),
                "data_freshness": self._check_data_freshness(),
            },
            "health_score": 0,
        }

    def scan_and_score(self) -> dict:
        result = self.full_scan()
        result["health_score"] = self._calculate_health_score(result["gaps"])
        result["recommendations"] = self._generate_recommendations(result["gaps"])
        return result

    def generate_gap_report(self) -> str:
        scan = self.scan_and_score()
        parts = [
            "# 🔍 Vault Health Report",
            f"*Scanned: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            f"*Total notes: {scan['total_notes']}*",
            f"*Health score: {scan['health_score']}/100*",
            "",
        ]

        gaps = scan["gaps"]

        stale = gaps["stale_notes"]
        if stale:
            parts.append(f"## ⏰ Dữ liệu cũ ({len(stale)} notes)")
            for note in stale[:10]:
                parts.append(f"- **{note['filename']}** — {note['days_old']} ngày, category: {note['category']}")
            parts.append("")

        orphans = gaps["orphan_notes"]
        if orphans:
            parts.append(f"## 🔗 Notes không liên kết ({len(orphans)} notes)")
            for note in orphans[:10]:
                parts.append(f"- {note['filename']} ({note['category']})")
            parts.append("")

        empty = gaps["empty_categories"]
        if empty:
            parts.append(f"## 📁 Categories trống ({len(empty)})")
            for cat in empty:
                parts.append(f"- {cat}")
            parts.append("")

        broken = gaps["broken_links"]
        if broken:
            parts.append(f"## ❌ Broken links ({len(broken)})")
            for link in broken[:10]:
                parts.append(f"- `[[{link['target']}]]` trong {link['source']}")
            parts.append("")

        tasks = gaps["open_tasks"]
        if tasks:
            parts.append(f"## ✅ Tasks quá hạn ({len(tasks)})")
            for task in tasks[:10]:
                parts.append(f"- **{task['title']}** — mở {task['days_open']} ngày")
            parts.append("")

        topic_gaps = gaps["topic_gaps"]
        if topic_gaps:
            parts.append(f"## 🧠 Topic gaps ({len(topic_gaps)})")
            for gap in topic_gaps[:10]:
                parts.append(f"- {gap['description']}")
            parts.append("")

        freshness = gaps["data_freshness"]
        if freshness:
            parts.append("## 📊 Data Freshness")
            for item in freshness:
                status_icon = "✅" if item["fresh"] else "⚠️"
                parts.append(f"- {status_icon} **{item['category']}**: last update {item['last_update'] or 'never'}, threshold {item['threshold_days']}d")
            parts.append("")

        if scan.get("recommendations"):
            parts.append("## 💡 Recommendations")
            for rec in scan["recommendations"]:
                parts.append(f"- {rec}")
            parts.append("")

        return "\n".join(parts)

    def get_research_prompts(self, max_prompts: int = 5) -> list[dict]:
        scan = self.scan_and_score()
        prompts = []

        for item in scan["gaps"].get("data_freshness", []):
            if not item["fresh"]:
                prompts.append({
                    "type": "data_refresh",
                    "priority": "high",
                    "category": item["category"],
                    "prompt": f"Pull latest {item['category']} data. Last update was {item['last_update'] or 'never'}.",
                    "action": f"dx-sync biz-loop prompt {item['category'].replace('-', '_')}",
                })

        for gap in scan["gaps"].get("topic_gaps", []):
            prompts.append({
                "type": "topic_research",
                "priority": "medium",
                "topic": gap.get("topic", ""),
                "prompt": gap.get("research_prompt", gap["description"]),
            })

        for task in scan["gaps"].get("open_tasks", []):
            if task["days_open"] > 14:
                prompts.append({
                    "type": "task_review",
                    "priority": "medium",
                    "task": task["title"],
                    "prompt": f"Review and update task: {task['title']} (open {task['days_open']} days). Close if done, update if in progress.",
                })

        prompts.sort(key=lambda p: {"high": 0, "medium": 1, "low": 2}.get(p.get("priority", "low"), 2))
        return prompts[:max_prompts]

    def _load_all_notes(self) -> list[dict]:
        notes = []
        all_dirs = {}
        all_dirs.update({k: v for k, v in CATEGORY_DIRS.items()})
        for key, subdir in BUSINESS_DIRS.items():
            all_dirs[key] = subdir

        for category, subdir in all_dirs.items():
            dir_path = self.memory_path / subdir
            if not dir_path.exists():
                continue
            for md_file in dir_path.glob("*.md"):
                parsed = self.writer._parse_vault_note(md_file)
                if parsed:
                    parsed["_category_dir"] = category
                    notes.append(parsed)

        return notes

    def _find_stale_notes(self, notes: list[dict]) -> list[dict]:
        stale = []
        now = datetime.now()

        for note in notes:
            created_str = note.get("created", "")
            if not created_str:
                continue
            try:
                created = datetime.fromisoformat(created_str)
            except ValueError:
                continue

            category = note.get("_category_dir", note.get("category", "learning"))
            threshold = STALE_THRESHOLDS.get(category, 30)
            days_old = (now - created).days

            if days_old > threshold:
                fm = note.get("frontmatter", {})
                if fm.get("status") in ("open", "in-progress", "active", "current"):
                    stale.append({
                        "filename": note["filename"],
                        "category": category,
                        "days_old": days_old,
                        "threshold": threshold,
                        "path": note.get("path", ""),
                    })

        stale.sort(key=lambda x: x["days_old"], reverse=True)
        return stale

    def _find_orphan_notes(self, notes: list[dict]) -> list[dict]:
        all_filenames = {n["filename"] for n in notes}
        linked_from = set()

        for note in notes:
            content = note.get("content", "")
            links = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)
            for link in links:
                linked_from.add(link.strip())

            fm = note.get("frontmatter", {})
            for link in fm.get("links", []):
                linked_from.add(link)

        orphans = []
        for note in notes:
            if note["filename"] not in linked_from:
                fm = note.get("frontmatter", {})
                has_links = bool(fm.get("links", []))
                content_links = re.findall(r"\[\[([^\]]+)\]\]", note.get("content", ""))
                if not has_links and not content_links:
                    orphans.append({
                        "filename": note["filename"],
                        "category": note.get("category", "unknown"),
                        "path": note.get("path", ""),
                    })

        return orphans

    def _find_empty_categories(self) -> list[str]:
        empty = []
        all_dirs = dict(CATEGORY_DIRS)
        for key, subdir in BUSINESS_DIRS.items():
            all_dirs[key] = subdir

        for category, subdir in all_dirs.items():
            dir_path = self.memory_path / subdir
            if not dir_path.exists():
                empty.append(category)
            elif not list(dir_path.glob("*.md")):
                empty.append(category)

        return empty

    def _find_broken_links(self, notes: list[dict]) -> list[dict]:
        all_filenames = {n["filename"].lower() for n in notes}
        broken = []

        for note in notes:
            content = note.get("content", "")
            links = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)
            for link in links:
                link_clean = link.strip()
                if link_clean.lower() not in all_filenames:
                    broken.append({
                        "source": note["filename"],
                        "target": link_clean,
                    })

        return broken

    def _find_undertaged_notes(self, notes: list[dict]) -> list[dict]:
        undertaged = []
        for note in notes:
            tags = note.get("tags", [])
            if len(tags) <= 1:
                undertaged.append({
                    "filename": note["filename"],
                    "category": note.get("category", "unknown"),
                    "tag_count": len(tags),
                })
        return undertaged

    def _find_stale_tasks(self, notes: list[dict]) -> list[dict]:
        stale_tasks = []
        now = datetime.now()

        for note in notes:
            if note.get("category") != "task":
                continue
            fm = note.get("frontmatter", {})
            if fm.get("status") not in ("open", "in-progress", None):
                continue

            created_str = note.get("created", "")
            if not created_str:
                continue
            try:
                created = datetime.fromisoformat(created_str)
                days_open = (now - created).days
            except ValueError:
                continue

            if days_open >= 7:
                stale_tasks.append({
                    "title": fm.get("title", note["filename"]),
                    "days_open": days_open,
                    "path": note.get("path", ""),
                })

        stale_tasks.sort(key=lambda x: x["days_open"], reverse=True)
        return stale_tasks

    def _find_topic_gaps(self, notes: list[dict]) -> list[dict]:
        all_tags = Counter()
        for note in notes:
            for tag in note.get("tags", []):
                all_tags[tag] += 1

        entity_names = set()
        for note in notes:
            if note.get("category") == "entity":
                entity_names.add(note["filename"])

        gaps = []

        expected_categories = set(CATEGORY_DIRS.keys())
        existing_categories = {n.get("category") for n in notes}
        for cat in expected_categories - existing_categories:
            gaps.append({
                "topic": cat,
                "description": f"Không có notes nào trong category '{cat}'",
                "research_prompt": f"Document current {cat} items for the vault.",
            })

        for entity in entity_names:
            entity_lower = entity.lower()
            mentioned = sum(
                1 for n in notes
                if n.get("category") != "entity" and entity_lower in n.get("content", "").lower()
            )
            if mentioned == 0:
                gaps.append({
                    "topic": entity,
                    "description": f"Entity '{entity}' exists but is never referenced in other notes",
                    "research_prompt": f"Research and document connections for entity: {entity}",
                })

        decision_count = sum(1 for n in notes if n.get("category") == "decision")
        learning_count = sum(1 for n in notes if n.get("category") == "learning")
        if decision_count > 0 and learning_count == 0:
            gaps.append({
                "topic": "learnings",
                "description": f"{decision_count} decisions recorded but no learnings — knowledge capture may be incomplete",
                "research_prompt": "Review recent decisions and extract key learnings.",
            })

        return gaps

    def _check_data_freshness(self) -> list[dict]:
        freshness = []
        now = datetime.now()

        for category, subdir in BUSINESS_DIRS.items():
            dir_path = self.memory_path / subdir
            threshold = STALE_THRESHOLDS.get(category, 14)

            if not dir_path.exists() or not list(dir_path.glob("*.md")):
                freshness.append({
                    "category": category,
                    "last_update": None,
                    "threshold_days": threshold,
                    "fresh": False,
                })
                continue

            latest = max(dir_path.glob("*.md"), key=os.path.getmtime)
            last_modified = datetime.fromtimestamp(os.path.getmtime(latest))
            days_since = (now - last_modified).days

            freshness.append({
                "category": category,
                "last_update": last_modified.strftime("%Y-%m-%d"),
                "threshold_days": threshold,
                "days_since_update": days_since,
                "fresh": days_since <= threshold,
            })

        return freshness

    def _calculate_health_score(self, gaps: dict) -> int:
        score = 100

        stale_count = len(gaps.get("stale_notes", []))
        score -= min(stale_count * 3, 20)

        orphan_count = len(gaps.get("orphan_notes", []))
        score -= min(orphan_count * 2, 15)

        empty_count = len(gaps.get("empty_categories", []))
        score -= min(empty_count * 5, 20)

        broken_count = len(gaps.get("broken_links", []))
        score -= min(broken_count * 3, 15)

        stale_task_count = len(gaps.get("open_tasks", []))
        score -= min(stale_task_count * 4, 15)

        stale_data = sum(1 for f in gaps.get("data_freshness", []) if not f.get("fresh"))
        score -= min(stale_data * 5, 15)

        return max(0, score)

    def _generate_recommendations(self, gaps: dict) -> list[str]:
        recs = []

        stale = gaps.get("stale_notes", [])
        if stale:
            recs.append(f"Review {len(stale)} stale notes — update status or archive outdated content.")

        open_tasks = gaps.get("open_tasks", [])
        if open_tasks:
            oldest = open_tasks[0]
            recs.append(f"Oldest open task '{oldest['title']}' has been open {oldest['days_open']} days — close or update.")

        empty = gaps.get("empty_categories", [])
        if empty:
            recs.append(f"Categories {', '.join(empty)} are empty — add content or remove from tracking.")

        stale_data = [f for f in gaps.get("data_freshness", []) if not f.get("fresh")]
        if stale_data:
            cats = ", ".join(d["category"] for d in stale_data)
            recs.append(f"Business data stale for: {cats} — run biz-loop to refresh.")

        broken = gaps.get("broken_links", [])
        if broken:
            recs.append(f"Fix {len(broken)} broken wiki links to improve vault connectivity.")

        topic_gaps = gaps.get("topic_gaps", [])
        if topic_gaps:
            recs.append(f"Found {len(topic_gaps)} topic gaps — use auto-research to fill them.")

        return recs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DX Vault — Knowledge Gap Detector")
    parser.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT_PATH", "/tmp/dx-vault-demo"))
    parser.add_argument("--memory-dir", default="DX-Memory")
    parser.add_argument("command", nargs="?", default="scan", choices=["scan", "report", "prompts"])
    parser.add_argument("--max-prompts", type=int, default=5)

    args = parser.parse_args()
    detector = GapDetector(args.vault, args.memory_dir)

    if args.command == "scan":
        result = detector.scan_and_score()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "report":
        print(detector.generate_gap_report())
    elif args.command == "prompts":
        prompts = detector.get_research_prompts(args.max_prompts)
        print(json.dumps(prompts, ensure_ascii=False, indent=2))

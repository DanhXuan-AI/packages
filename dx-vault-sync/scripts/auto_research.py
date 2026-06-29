#!/usr/bin/env python3
"""
DX Vault Sync — Phase 4: Auto-Research Engine
Generates research prompts from knowledge gaps, executes via MCP tools
(Bigdata.com, Supermetrics, Web Search), and stores results in vault.

Architecture:
  GapDetector → research prompts → this engine → MCP prompts / direct fill → vault
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from gap_detector import GapDetector
from vault_writer import VaultWriter

RESEARCH_SOURCES = {
    "bigdata": {
        "name": "Bigdata.com",
        "type": "mcp",
        "tools": ["mcp__Bigdata_com__bigdata_search", "mcp__Bigdata_com__bigdata_company_tearsheet"],
        "best_for": ["market-intel", "competitors", "company_research"],
    },
    "supermetrics": {
        "name": "Supermetrics",
        "type": "mcp",
        "tools": ["mcp__Supermetrics_Marketing_Analytics__data_query"],
        "best_for": ["marketing-analytics", "ad_performance"],
    },
    "web": {
        "name": "Web Search",
        "type": "tool",
        "tools": ["WebSearch", "WebFetch"],
        "best_for": ["general", "news", "trends", "topic_research"],
    },
}

RESEARCH_TEMPLATES = {
    "data_refresh": {
        "market-intel": (
            "Pull latest market intelligence:\n"
            "1. Use `mcp__Bigdata_com__bigdata_search` with query about the company/market\n"
            "2. Get company tearsheet if entity ID is known\n"
            "3. Save results: `dx-sync biz market --source bigdata --data '<json>'`"
        ),
        "marketing-analytics": (
            "Pull latest marketing data:\n"
            "1. Use `mcp__Supermetrics_Marketing_Analytics__data_source_discovery` to list sources\n"
            "2. Query performance data with `data_query`\n"
            "3. Save: `dx-sync biz marketing --source supermetrics --data '<json>'`"
        ),
        "finance-snapshots": (
            "Update finance snapshot:\n"
            "1. Gather latest revenue, profit, orders, customers data\n"
            "2. Save: `dx-sync biz finance --source manual --data '<json>'`"
        ),
        "competitors": (
            "Update competitor intelligence:\n"
            "1. Use `mcp__Bigdata_com__bigdata_search` for competitor news\n"
            "2. Save: `dx-sync biz competitor --source bigdata --data '<json>'`"
        ),
    },
    "topic_research": (
        "Research topic: {topic}\n"
        "1. Search vault first: `dx-sync context --query \"{topic}\"`\n"
        "2. Use WebSearch for current information\n"
        "3. Sync findings: `dx-sync sync \"<findings>\"`"
    ),
    "task_review": (
        "Review task: {task}\n"
        "1. Check current status and context\n"
        "2. Update or close: `dx-sync sync \"Task update: {task} — <status>\"`"
    ),
}


class AutoResearch:
    def __init__(self, vault_path: str, memory_dir: str = "DX-Memory"):
        self.vault_path = Path(vault_path).expanduser()
        self.memory_path = self.vault_path / memory_dir
        self.detector = GapDetector(str(self.vault_path), memory_dir)
        self.writer = VaultWriter(str(self.vault_path), memory_dir)
        self.research_log_path = self.memory_path / "_index" / "research_log.json"

    def analyze_and_plan(self, max_items: int = 10) -> dict:
        scan = self.detector.scan_and_score()
        prompts = self.detector.get_research_prompts(max_items)

        plan = {
            "timestamp": datetime.now().isoformat(),
            "health_score": scan["health_score"],
            "total_gaps": sum(len(v) if isinstance(v, list) else 0 for v in scan["gaps"].values()),
            "research_items": [],
        }

        for prompt in prompts:
            item = self._enrich_prompt(prompt)
            plan["research_items"].append(item)

        return plan

    def generate_claude_prompt(self, research_item: Optional[dict] = None) -> str:
        if research_item:
            return self._build_single_prompt(research_item)

        plan = self.analyze_and_plan(max_items=5)
        if not plan["research_items"]:
            return "No knowledge gaps detected. Vault is healthy!"

        parts = [
            "# DX Auto-Research — Knowledge Gap Fill",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            f"*Health score: {plan['health_score']}/100 | Gaps found: {plan['total_gaps']}*",
            "",
            "Execute the following research tasks in order:",
            "",
        ]

        for i, item in enumerate(plan["research_items"], 1):
            parts.append(f"## Task {i}: {item['title']}")
            parts.append(f"Priority: {item['priority']} | Type: {item['type']}")
            parts.append(f"Source: {item.get('suggested_source', 'any')}")
            parts.append("")
            parts.append(item["instructions"])
            parts.append("")

        parts.extend([
            "---",
            "After completing all tasks, run: `dx-sync gap-scan` to verify improvements.",
        ])

        return "\n".join(parts)

    def generate_loop_script(self) -> str:
        plan = self.analyze_and_plan()
        if not plan["research_items"]:
            return "echo 'No gaps to fill. Vault health: OK'"

        lines = [
            "#!/usr/bin/env bash",
            "# DX Auto-Research Loop — Generated " + datetime.now().strftime("%Y-%m-%d %H:%M"),
            'set -euo pipefail',
            "",
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            'VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/ObsidianVault}"',
            "",
        ]

        for i, item in enumerate(plan["research_items"], 1):
            if item["type"] == "data_refresh":
                action = item.get("action", "")
                if action:
                    lines.append(f'echo "Step {i}: {item["title"]}"')
                    lines.append(action)
                    lines.append("")

        lines.extend([
            '# Final gap scan',
            'echo "Running post-research gap scan..."',
            'python3 "$SCRIPT_DIR/gap_detector.py" --vault "$VAULT_PATH" report',
        ])

        return "\n".join(lines)

    def store_research_result(self, topic: str, findings: str, source: str = "auto-research") -> Path:
        insight = {
            "id": f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "category": "learning",
            "title": f"Research: {topic}",
            "content": findings,
            "tags": ["auto-research", "gap-fill", source],
            "links": [],
            "source": f"auto-research:{source}",
            "timestamp": datetime.now().isoformat(),
            "confidence": 0.7,
        }

        path = self.writer.write_insight(insight)
        self._log_research(topic, source, str(path))
        return path

    def get_research_history(self, limit: int = 20) -> list[dict]:
        if not self.research_log_path.exists():
            return []
        try:
            log = json.loads(self.research_log_path.read_text(encoding="utf-8"))
            return log.get("entries", [])[-limit:]
        except (json.JSONDecodeError, OSError):
            return []

    def _enrich_prompt(self, prompt: dict) -> dict:
        prompt_type = prompt.get("type", "topic_research")
        category = prompt.get("category", "")

        if prompt_type == "data_refresh" and category in RESEARCH_TEMPLATES.get("data_refresh", {}):
            instructions = RESEARCH_TEMPLATES["data_refresh"][category]
            source = self._suggest_source(category)
        elif prompt_type == "topic_research":
            topic = prompt.get("topic", "")
            instructions = RESEARCH_TEMPLATES["topic_research"].format(topic=topic)
            source = "web"
        elif prompt_type == "task_review":
            task = prompt.get("task", "")
            instructions = RESEARCH_TEMPLATES["task_review"].format(task=task)
            source = "manual"
        else:
            instructions = prompt.get("prompt", "Research this topic.")
            source = "any"

        return {
            "title": prompt.get("prompt", prompt.get("topic", "Research item"))[:80],
            "type": prompt_type,
            "priority": prompt.get("priority", "medium"),
            "category": category,
            "instructions": instructions,
            "suggested_source": source,
            "action": prompt.get("action", ""),
        }

    def _suggest_source(self, category: str) -> str:
        for source_key, source_info in RESEARCH_SOURCES.items():
            if category in source_info.get("best_for", []):
                return source_key
        return "web"

    def _build_single_prompt(self, item: dict) -> str:
        parts = [
            f"# Research: {item.get('title', 'Unknown')}",
            f"*Priority: {item.get('priority', 'medium')}*",
            "",
            item.get("instructions", item.get("prompt", "")),
            "",
            "---",
            "Save results to vault when done.",
        ]
        return "\n".join(parts)

    def _log_research(self, topic: str, source: str, result_path: str):
        log = {"entries": []}
        if self.research_log_path.exists():
            try:
                log = json.loads(self.research_log_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        log["entries"].append({
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "source": source,
            "result_path": result_path,
        })

        log["entries"] = log["entries"][-200:]
        self.research_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.research_log_path.write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DX Vault — Auto-Research Engine")
    parser.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT_PATH", "/tmp/dx-vault-demo"))
    parser.add_argument("--memory-dir", default="DX-Memory")
    parser.add_argument("command", nargs="?", default="plan", choices=["plan", "prompt", "script", "history", "store"])
    parser.add_argument("--topic", default="")
    parser.add_argument("--findings", default="")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--max-items", type=int, default=5)

    args = parser.parse_args()
    engine = AutoResearch(args.vault, args.memory_dir)

    if args.command == "plan":
        plan = engine.analyze_and_plan(args.max_items)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    elif args.command == "prompt":
        print(engine.generate_claude_prompt())
    elif args.command == "script":
        print(engine.generate_loop_script())
    elif args.command == "history":
        history = engine.get_research_history()
        print(json.dumps(history, ensure_ascii=False, indent=2))
    elif args.command == "store":
        if args.topic and args.findings:
            path = engine.store_research_result(args.topic, args.findings, args.source)
            print(f"Stored: {path}")
        else:
            print("Error: --topic and --findings required for store command")

#!/usr/bin/env python3
"""
DX Vault Sync — Phase 2: Business Data Loop Runner
Generates Claude Code prompts to pull data from MCP sources,
then processes and stores results in Obsidian Vault.

This script outputs structured prompts that Claude Code executes
to interact with MCP tools (Bigdata.com, Supermetrics, etc.).
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from business_collector import BusinessCollector


LOOP_TASKS = {
    "market-scan": {
        "label": "Market Intelligence Scan",
        "description": "Pull company/market data from Bigdata.com",
        "mcp_source": "bigdata",
        "frequency": "daily",
        "prompt_template": """Use the Bigdata.com MCP tools to research the following:

1. Call `mcp__Bigdata_com__find_securities` to find entity ID for: {entity}
2. Call `mcp__Bigdata_com__bigdata_company_tearsheet` with the entity ID
3. Call `mcp__Bigdata_com__bigdata_sentiment_tearsheet` with the entity ID
4. Call `mcp__Bigdata_com__bigdata_events_calendar` for upcoming events

After collecting data, format it as JSON with this structure:
{{
  "company_name": "...",
  "metrics": {{"market_cap": ..., "pe_ratio": ..., "eps": ..., "price": ...}},
  "sentiment": {{"score": ..., "trend": "...", "summary": "..."}},
  "events": [{{"date": "...", "title": "..."}}],
  "raw_summary": "..."
}}

Then run: python3 {script_dir}/business_collector.py --vault {vault} --type market --source bigdata --data '<json>'""",
    },
    "marketing-pull": {
        "label": "Marketing Analytics Pull",
        "description": "Pull marketing performance from Supermetrics",
        "mcp_source": "supermetrics",
        "frequency": "daily",
        "prompt_template": """Use the Supermetrics MCP tools to pull marketing data:

1. Call `mcp__Supermetrics_Marketing_Analytics__data_source_discovery` to list available sources
2. For each connected ad platform (Google Ads, Facebook Ads, etc.):
   a. Call `mcp__Supermetrics_Marketing_Analytics__accounts_discovery` with the ds_id
   b. Call `mcp__Supermetrics_Marketing_Analytics__field_discovery` with the ds_id
   c. Call `mcp__Supermetrics_Marketing_Analytics__data_query` with:
      - fields: spend, impressions, clicks, conversions, revenue, ctr, cpc, roas
      - date range: last 30 days
      - group by: campaign name
3. Call `mcp__Supermetrics_Marketing_Analytics__get_async_query_results` to get results

Format the results as JSON:
{{
  "platform": "Google Ads / Facebook Ads / ...",
  "period": "{period}",
  "totals": {{"spend": ..., "impressions": ..., "clicks": ..., "conversions": ..., "revenue": ..., "ctr": ..., "roas": ...}},
  "campaigns": [{{"name": "...", "spend": ..., "clicks": ..., "conversions": ..., "roas": ...}}]
}}

Then run: python3 {script_dir}/business_collector.py --vault {vault} --type marketing --source supermetrics --data '<json>'""",
    },
    "news-scan": {
        "label": "Business News Scan",
        "description": "Search for relevant business news via Bigdata.com",
        "mcp_source": "bigdata",
        "frequency": "daily",
        "prompt_template": """Use Bigdata.com MCP to scan for relevant business news:

1. Call `mcp__Bigdata_com__bigdata_search` with query: "{query}"
   - Use smart mode for comprehensive results
   - Focus on recent news (last 7 days)

2. For each relevant result, extract:
   - Title, date, source
   - Key takeaways
   - Impact assessment

Format as JSON:
{{
  "company_name": "{entity}",
  "raw_summary": "Summary of findings...",
  "events": [{{"date": "...", "title": "..."}}],
  "metrics": {{}}
}}

Then run: python3 {script_dir}/business_collector.py --vault {vault} --type market --source bigdata --data '<json>'""",
    },
    "finance-snapshot": {
        "label": "Financial Snapshot",
        "description": "Record current business financial metrics",
        "mcp_source": "manual",
        "frequency": "weekly",
        "prompt_template": """Record current business financial metrics.

Ask or gather the following data points for {entity}:
- Doanh thu (Revenue) for current period
- Chi phí (Costs)
- Lợi nhuận (Profit)
- Số đơn hàng (Orders)
- Khách hàng mới (New customers)
- Tỷ lệ chốt (Close rate)

Also gather comparison data from previous period.

Format as JSON:
{{
  "entity": "{entity}",
  "period": "{period}",
  "revenue": ...,
  "costs": ...,
  "profit": ...,
  "orders": ...,
  "customers": ...,
  "close_rate": ...,
  "previous_period": {{
    "revenue": ...,
    "profit": ...,
    "orders": ...,
    "customers": ...
  }},
  "notes": "Any notable observations...",
  "action_items": ["Item 1", "Item 2"]
}}

Then run: python3 {script_dir}/business_collector.py --vault {vault} --type finance --source manual --data '<json>'""",
    },
    "daily-report": {
        "label": "Daily Business Report",
        "description": "Generate daily summary from all collected data",
        "mcp_source": "vault",
        "frequency": "daily",
        "prompt_template": """Generate a daily business report by:

1. Read recent notes from the vault:
   - {vault}/DX-Memory/business/market-intel/ (latest)
   - {vault}/DX-Memory/business/marketing-analytics/ (latest)
   - {vault}/DX-Memory/business/finance-snapshots/ (latest)
   - {vault}/DX-Memory/business/alerts/ (unread)

2. Compile a summary with:
   - Key financial metrics
   - Marketing performance highlights
   - Market intelligence updates
   - Active alerts
   - Recommended actions

Format as JSON:
{{
  "finance": {{"revenue": ..., "profit": ..., "orders": ...}},
  "marketing": {{"spend": ..., "roas": ..., "conversions": ...}},
  "market": ["Key market update 1", "Key market update 2"],
  "alerts": ["Alert 1", "Alert 2"],
  "action_items": ["Action 1", "Action 2"]
}}

Then run: python3 {script_dir}/business_collector.py --vault {vault} --type report --data '<json>'""",
    },
}


class BusinessLoop:
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).expanduser()
        self.script_dir = Path(__file__).parent
        self.collector = BusinessCollector(str(self.vault_path))

    def generate_prompt(
        self,
        task_key: str,
        entity: str = "DX Advisory",
        query: str = "",
        period: str = "",
    ) -> str:
        if task_key not in LOOP_TASKS:
            return f"Unknown task: {task_key}. Available: {', '.join(LOOP_TASKS.keys())}"

        task = LOOP_TASKS[task_key]
        if not period:
            period = datetime.now().strftime("%Y-%m")

        prompt = task["prompt_template"].format(
            entity=entity,
            query=query or entity,
            period=period,
            vault=str(self.vault_path),
            script_dir=str(self.script_dir),
        )

        return prompt

    def generate_full_loop(
        self,
        entities: list[str],
        tasks: list[str] | None = None,
    ) -> str:
        if tasks is None:
            tasks = list(LOOP_TASKS.keys())

        parts = [
            "# DX Business Data Loop",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            f"*Entities: {', '.join(entities)}*",
            "",
        ]

        step = 1
        for task_key in tasks:
            if task_key not in LOOP_TASKS:
                continue
            task = LOOP_TASKS[task_key]
            for entity in entities:
                parts.append(f"## Step {step}: {task['label']} — {entity}")
                parts.append(f"*Source: {task['mcp_source']} | Frequency: {task['frequency']}*")
                parts.append("")
                parts.append(self.generate_prompt(task_key, entity=entity))
                parts.append("")
                parts.append("---")
                parts.append("")
                step += 1

        return "\n".join(parts)

    def list_tasks(self) -> list[dict]:
        return [
            {
                "key": key,
                "label": task["label"],
                "description": task["description"],
                "mcp_source": task["mcp_source"],
                "frequency": task["frequency"],
            }
            for key, task in LOOP_TASKS.items()
        ]

    def get_status(self) -> dict:
        return {
            "vault_path": str(self.vault_path),
            "business_stats": self.collector.get_business_stats(),
            "available_tasks": self.list_tasks(),
            "timestamp": datetime.now().isoformat(),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="DX Business Data Loop Runner")
    parser.add_argument(
        "--vault",
        default=os.environ.get("OBSIDIAN_VAULT_PATH", "/home/user/ObsidianVault"),
    )

    subparsers = parser.add_subparsers(dest="command")

    prompt_parser = subparsers.add_parser("prompt", help="Generate a single task prompt")
    prompt_parser.add_argument("task", choices=list(LOOP_TASKS.keys()))
    prompt_parser.add_argument("--entity", default="DX Advisory")
    prompt_parser.add_argument("--query", default="")
    prompt_parser.add_argument("--period", default="")

    loop_parser = subparsers.add_parser("loop", help="Generate full loop for entities")
    loop_parser.add_argument("--entities", nargs="+", default=["DX Advisory"])
    loop_parser.add_argument("--tasks", nargs="+", default=None)

    subparsers.add_parser("list", help="List available tasks")
    subparsers.add_parser("status", help="Show business loop status")

    args = parser.parse_args()
    runner = BusinessLoop(args.vault)

    if args.command == "prompt":
        print(runner.generate_prompt(args.task, entity=args.entity, query=args.query, period=args.period))
    elif args.command == "loop":
        print(runner.generate_full_loop(args.entities, args.tasks))
    elif args.command == "list":
        tasks = runner.list_tasks()
        print(json.dumps(tasks, ensure_ascii=False, indent=2))
    elif args.command == "status":
        status = runner.get_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

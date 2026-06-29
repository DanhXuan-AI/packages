#!/usr/bin/env python3
"""
DX Vault Sync — Phase 2: Business Data Collector
Processes business data from MCP sources (Bigdata.com, Supermetrics, etc.)
and writes structured reports to Obsidian Vault.

Architecture:
  Claude Code (MCP tools) → JSON data → this script → Obsidian Vault notes

Claude Code pulls data via MCP, then pipes it here for processing & storage.
"""

import json
import sys
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from vault_writer import VaultWriter


BUSINESS_DIRS = {
    "market-intel": "Thông tin thị trường",
    "marketing-analytics": "Phân tích Marketing",
    "finance-snapshots": "Ảnh chụp tài chính",
    "alerts": "Cảnh báo",
    "competitors": "Đối thủ cạnh tranh",
    "reports": "Báo cáo tổng hợp",
}


class BusinessCollector:
    def __init__(self, vault_path: str, memory_dir: str = "DX-Memory"):
        self.vault_path = Path(vault_path).expanduser()
        self.memory_path = self.vault_path / memory_dir
        self.business_path = self.memory_path / "business"
        self.writer = VaultWriter(str(self.vault_path), memory_dir)
        self._ensure_dirs()

    def _ensure_dirs(self):
        for subdir in BUSINESS_DIRS:
            (self.business_path / subdir).mkdir(parents=True, exist_ok=True)
        (self.business_path / "_snapshots").mkdir(parents=True, exist_ok=True)

    def process_market_intel(self, data: dict, source: str = "bigdata") -> Path:
        """Process company/market data from Bigdata.com tearsheets."""
        company = data.get("company_name", data.get("name", "Unknown"))
        timestamp = datetime.now().strftime("%Y-%m-%d")

        metrics = data.get("metrics", {})
        sentiment = data.get("sentiment", {})
        events = data.get("events", [])

        frontmatter = {
            "type": "market-intel",
            "company": company,
            "source": source,
            "created": datetime.now().isoformat(),
            "tags": ["market-intel", "business", source]
                + [company.lower().replace(" ", "-")],
            "status": "current",
            "auto_synced": True,
        }

        if metrics:
            frontmatter["key_metrics"] = {
                k: v for k, v in metrics.items() if isinstance(v, (int, float, str))
            }

        content_parts = [f"# {company} — Market Intelligence", f"*Updated: {timestamp}*", ""]

        if metrics:
            content_parts.append("## Chỉ số chính")
            for key, val in metrics.items():
                label = self._format_metric_label(key)
                content_parts.append(f"- **{label}**: {val}")
            content_parts.append("")

        if sentiment:
            content_parts.append("## Sentiment")
            score = sentiment.get("score", "N/A")
            trend = sentiment.get("trend", "N/A")
            content_parts.append(f"- Score: {score}")
            content_parts.append(f"- Trend: {trend}")
            if sentiment.get("summary"):
                content_parts.append(f"- Summary: {sentiment['summary']}")
            content_parts.append("")

        if events:
            content_parts.append("## Sự kiện gần đây")
            for event in events[:10]:
                date = event.get("date", "")
                title = event.get("title", event.get("name", ""))
                content_parts.append(f"- [{date}] {title}")
            content_parts.append("")

        if data.get("raw_summary"):
            content_parts.append("## Tóm tắt")
            content_parts.append(data["raw_summary"])
            content_parts.append("")

        content_parts.extend([
            "---",
            f"*Auto-synced from {source} by DX Vault Sync at {datetime.now().strftime('%H:%M:%S')}*",
        ])

        filename = self._safe_filename(f"{timestamp}_{company}")
        filepath = self.business_path / "market-intel" / f"{filename}.md"
        filepath = self._avoid_overwrite(filepath)

        self._write_note(filepath, frontmatter, "\n".join(content_parts))
        self._save_snapshot("market-intel", company, data)
        return filepath

    def process_marketing_analytics(self, data: dict, source: str = "supermetrics") -> Path:
        """Process marketing performance data from Supermetrics."""
        platform = data.get("platform", data.get("source", "unknown"))
        period = data.get("period", datetime.now().strftime("%Y-%m"))
        timestamp = datetime.now().strftime("%Y-%m-%d")

        campaigns = data.get("campaigns", [])
        totals = data.get("totals", data.get("summary", {}))
        channels = data.get("channels", [])

        frontmatter = {
            "type": "marketing-analytics",
            "platform": platform,
            "period": period,
            "source": source,
            "created": datetime.now().isoformat(),
            "tags": ["marketing", "analytics", platform.lower(), source],
            "status": "current",
            "auto_synced": True,
        }

        if totals:
            frontmatter["kpi"] = {
                k: v for k, v in totals.items() if isinstance(v, (int, float))
            }

        content_parts = [
            f"# Marketing Analytics — {platform}",
            f"*Period: {period} | Updated: {timestamp}*",
            "",
        ]

        if totals:
            content_parts.append("## KPI Tổng quan")
            kpi_map = {
                "spend": "Chi phí",
                "impressions": "Lượt hiển thị",
                "clicks": "Lượt click",
                "conversions": "Chuyển đổi",
                "revenue": "Doanh thu",
                "roas": "ROAS",
                "ctr": "CTR",
                "cpc": "CPC",
                "cpa": "CPA",
                "cost": "Chi phí",
            }
            for key, val in totals.items():
                label = kpi_map.get(key.lower(), self._format_metric_label(key))
                formatted = self._format_number(val)
                content_parts.append(f"- **{label}**: {formatted}")
            content_parts.append("")

        if campaigns:
            content_parts.append("## Campaigns")
            content_parts.append("| Campaign | Spend | Clicks | Conv | ROAS |")
            content_parts.append("|---|---|---|---|---|")
            for camp in campaigns[:20]:
                name = camp.get("name", "N/A")
                spend = self._format_number(camp.get("spend", camp.get("cost", 0)))
                clicks = camp.get("clicks", "N/A")
                conv = camp.get("conversions", camp.get("conv", "N/A"))
                roas = camp.get("roas", "N/A")
                content_parts.append(f"| {name} | {spend} | {clicks} | {conv} | {roas} |")
            content_parts.append("")

        if channels:
            content_parts.append("## Channels")
            for ch in channels:
                name = ch.get("name", ch.get("channel", ""))
                content_parts.append(f"### {name}")
                for k, v in ch.items():
                    if k not in ("name", "channel"):
                        content_parts.append(f"- {self._format_metric_label(k)}: {v}")
                content_parts.append("")

        content_parts.extend([
            "---",
            f"*Auto-synced from {source} by DX Vault Sync at {datetime.now().strftime('%H:%M:%S')}*",
        ])

        filename = self._safe_filename(f"{timestamp}_{platform}_{period}")
        filepath = self.business_path / "marketing-analytics" / f"{filename}.md"
        filepath = self._avoid_overwrite(filepath)

        self._write_note(filepath, frontmatter, "\n".join(content_parts))
        self._save_snapshot("marketing-analytics", f"{platform}_{period}", data)
        return filepath

    def process_finance_snapshot(self, data: dict, source: str = "manual") -> Path:
        """Process financial snapshot data (revenue, costs, profit, etc.)."""
        period = data.get("period", datetime.now().strftime("%Y-%m"))
        entity = data.get("entity", data.get("business", "DX Advisory"))
        timestamp = datetime.now().strftime("%Y-%m-%d")

        revenue = data.get("revenue", data.get("doanh_thu"))
        costs = data.get("costs", data.get("chi_phi"))
        profit = data.get("profit", data.get("loi_nhuan"))
        orders = data.get("orders", data.get("don_hang"))
        customers = data.get("customers", data.get("khach_hang"))
        close_rate = data.get("close_rate", data.get("ty_le_chot"))

        prev = data.get("previous_period", {})

        frontmatter = {
            "type": "finance-snapshot",
            "entity": entity,
            "period": period,
            "source": source,
            "created": datetime.now().isoformat(),
            "tags": ["finance", "snapshot", entity.lower().replace(" ", "-")],
            "status": "current",
            "auto_synced": True,
        }

        kpi = {}
        if revenue is not None:
            kpi["revenue"] = revenue
        if profit is not None:
            kpi["profit"] = profit
        if orders is not None:
            kpi["orders"] = orders
        if customers is not None:
            kpi["customers"] = customers
        if close_rate is not None:
            kpi["close_rate"] = close_rate
        if kpi:
            frontmatter["kpi"] = kpi

        content_parts = [
            f"# Financial Snapshot — {entity}",
            f"*Period: {period} | Updated: {timestamp}*",
            "",
            "## Chỉ số kinh doanh",
        ]

        metrics_display = [
            ("Doanh thu", revenue, prev.get("revenue")),
            ("Chi phí", costs, prev.get("costs")),
            ("Lợi nhuận", profit, prev.get("profit")),
            ("Số đơn", orders, prev.get("orders")),
            ("Khách hàng mới", customers, prev.get("customers")),
            ("Tỷ lệ chốt", close_rate, prev.get("close_rate")),
        ]

        for label, current, previous in metrics_display:
            if current is None:
                continue
            line = f"- **{label}**: {self._format_number(current)}"
            if previous is not None:
                change = self._calc_change(current, previous)
                emoji = "📈" if change >= 0 else "📉"
                line += f" {emoji} ({change:+.1f}% vs kỳ trước)"
            content_parts.append(line)

        content_parts.append("")

        if data.get("notes"):
            content_parts.append("## Ghi chú")
            content_parts.append(data["notes"])
            content_parts.append("")

        if data.get("action_items"):
            content_parts.append("## Hành động cần thiết")
            for item in data["action_items"]:
                content_parts.append(f"- [ ] {item}")
            content_parts.append("")

        alerts = self._detect_anomalies(data, prev)
        if alerts:
            content_parts.append("## Cảnh báo tự động")
            for alert in alerts:
                content_parts.append(f"- ⚠️ {alert}")
            content_parts.append("")

        content_parts.extend([
            "---",
            f"*Auto-synced by DX Vault Sync at {datetime.now().strftime('%H:%M:%S')}*",
        ])

        filename = self._safe_filename(f"{timestamp}_{entity}_{period}")
        filepath = self.business_path / "finance-snapshots" / f"{filename}.md"
        filepath = self._avoid_overwrite(filepath)

        self._write_note(filepath, frontmatter, "\n".join(content_parts))
        self._save_snapshot("finance", f"{entity}_{period}", data)

        if alerts:
            self._write_alerts(alerts, entity, period)

        return filepath

    def process_competitor_intel(self, data: dict, source: str = "bigdata") -> Path:
        """Process competitor intelligence data."""
        competitor = data.get("name", data.get("company", "Unknown"))
        timestamp = datetime.now().strftime("%Y-%m-%d")

        frontmatter = {
            "type": "competitor-intel",
            "competitor": competitor,
            "source": source,
            "created": datetime.now().isoformat(),
            "tags": ["competitor", "intel", competitor.lower().replace(" ", "-"), source],
            "status": "current",
            "auto_synced": True,
        }

        content_parts = [
            f"# Competitor Intel — {competitor}",
            f"*Updated: {timestamp}*",
            "",
        ]

        if data.get("overview"):
            content_parts.append("## Tổng quan")
            content_parts.append(data["overview"])
            content_parts.append("")

        if data.get("strengths"):
            content_parts.append("## Điểm mạnh")
            for s in data["strengths"]:
                content_parts.append(f"- {s}")
            content_parts.append("")

        if data.get("weaknesses"):
            content_parts.append("## Điểm yếu")
            for w in data["weaknesses"]:
                content_parts.append(f"- {w}")
            content_parts.append("")

        if data.get("recent_moves"):
            content_parts.append("## Động thái gần đây")
            for move in data["recent_moves"]:
                content_parts.append(f"- {move}")
            content_parts.append("")

        if data.get("metrics"):
            content_parts.append("## Chỉ số")
            for k, v in data["metrics"].items():
                content_parts.append(f"- **{self._format_metric_label(k)}**: {v}")
            content_parts.append("")

        content_parts.extend([
            "---",
            f"*Auto-synced from {source} by DX Vault Sync at {datetime.now().strftime('%H:%M:%S')}*",
        ])

        filename = self._safe_filename(f"{timestamp}_{competitor}")
        filepath = self.business_path / "competitors" / f"{filename}.md"
        filepath = self._avoid_overwrite(filepath)

        self._write_note(filepath, frontmatter, "\n".join(content_parts))
        return filepath

    def generate_daily_report(self, data: dict) -> Path:
        """Generate a daily business summary report from all available data."""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        day_name = datetime.now().strftime("%A")

        frontmatter = {
            "type": "daily-report",
            "date": timestamp,
            "created": datetime.now().isoformat(),
            "tags": ["report", "daily", "business"],
            "status": "current",
            "auto_synced": True,
        }

        content_parts = [
            f"# Daily Business Report — {timestamp} ({day_name})",
            "",
        ]

        if data.get("finance"):
            content_parts.append("## Tài chính")
            fin = data["finance"]
            for k, v in fin.items():
                content_parts.append(f"- **{self._format_metric_label(k)}**: {self._format_number(v)}")
            content_parts.append("")

        if data.get("marketing"):
            content_parts.append("## Marketing")
            mkt = data["marketing"]
            for k, v in mkt.items():
                content_parts.append(f"- **{self._format_metric_label(k)}**: {self._format_number(v)}")
            content_parts.append("")

        if data.get("market"):
            content_parts.append("## Thị trường")
            for item in data["market"]:
                content_parts.append(f"- {item}")
            content_parts.append("")

        if data.get("alerts"):
            content_parts.append("## Cảnh báo")
            for alert in data["alerts"]:
                content_parts.append(f"- ⚠️ {alert}")
            content_parts.append("")

        if data.get("action_items"):
            content_parts.append("## Hành động")
            for item in data["action_items"]:
                content_parts.append(f"- [ ] {item}")
            content_parts.append("")

        existing = self._load_recent_snapshots()
        if existing:
            content_parts.append("## Xu hướng (7 ngày)")
            for key, values in existing.items():
                if len(values) >= 2:
                    trend = "📈" if values[-1] > values[-2] else "📉" if values[-1] < values[-2] else "➡️"
                    content_parts.append(f"- {self._format_metric_label(key)}: {trend} {values[-1]}")
            content_parts.append("")

        content_parts.extend([
            "---",
            f"*Generated by DX Vault Sync at {datetime.now().strftime('%H:%M:%S')}*",
        ])

        filename = f"{timestamp}_daily_report"
        filepath = self.business_path / "reports" / f"{filename}.md"
        filepath = self._avoid_overwrite(filepath)

        self._write_note(filepath, frontmatter, "\n".join(content_parts))
        return filepath

    def get_business_stats(self) -> dict:
        """Get statistics about business data in the vault."""
        stats = {"total_notes": 0, "categories": {}, "latest_by_category": {}}

        for subdir, label in BUSINESS_DIRS.items():
            dir_path = self.business_path / subdir
            if not dir_path.exists():
                continue
            files = sorted(dir_path.glob("*.md"), key=os.path.getmtime, reverse=True)
            count = len(files)
            stats["categories"][subdir] = {"count": count, "label": label}
            stats["total_notes"] += count
            if files:
                stats["latest_by_category"][subdir] = {
                    "file": files[0].name,
                    "modified": datetime.fromtimestamp(files[0].stat().st_mtime).isoformat(),
                }

        return stats

    def _detect_anomalies(self, current: dict, previous: dict) -> list[str]:
        alerts = []
        threshold = 20

        checks = [
            ("revenue", "Doanh thu"),
            ("profit", "Lợi nhuận"),
            ("orders", "Số đơn"),
            ("customers", "Khách hàng"),
        ]

        for key, label in checks:
            curr_val = current.get(key, current.get(self._vn_key(key)))
            prev_val = previous.get(key)
            if curr_val is not None and prev_val is not None and prev_val != 0:
                change = self._calc_change(curr_val, prev_val)
                if abs(change) >= threshold:
                    direction = "tăng" if change > 0 else "giảm"
                    alerts.append(
                        f"{label} {direction} {abs(change):.1f}% "
                        f"({self._format_number(prev_val)} → {self._format_number(curr_val)})"
                    )

        return alerts

    def _write_alerts(self, alerts: list[str], entity: str, period: str):
        import yaml

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        frontmatter = {
            "type": "alert",
            "entity": entity,
            "period": period,
            "severity": "warning",
            "created": datetime.now().isoformat(),
            "tags": ["alert", "anomaly", "auto-detected"],
            "status": "unread",
            "auto_synced": True,
        }

        content_parts = [
            f"# Cảnh báo kinh doanh — {entity}",
            f"*Period: {period} | Detected: {timestamp}*",
            "",
        ]
        for alert in alerts:
            content_parts.append(f"- ⚠️ {alert}")
        content_parts.extend([
            "",
            "---",
            f"*Auto-detected by DX Vault Sync*",
        ])

        filename = self._safe_filename(f"{timestamp}_alert_{entity}")
        filepath = self.business_path / "alerts" / f"{filename}.md"
        self._write_note(filepath, frontmatter, "\n".join(content_parts))

    def _write_note(self, filepath: Path, frontmatter: dict, content: str):
        import yaml

        parts = [
            "---",
            yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip(),
            "---",
            "",
            content,
        ]
        filepath.write_text("\n".join(parts), encoding="utf-8")

    def _save_snapshot(self, category: str, key: str, data: dict):
        snapshot_dir = self.business_path / "_snapshots"
        snapshot_file = snapshot_dir / f"{category}.json"

        snapshots = {}
        if snapshot_file.exists():
            try:
                snapshots = json.loads(snapshot_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        safe_key = key.replace(" ", "_").lower()
        if safe_key not in snapshots:
            snapshots[safe_key] = []

        snapshots[safe_key].append({
            "timestamp": datetime.now().isoformat(),
            "data": {k: v for k, v in data.items() if isinstance(v, (int, float, str, bool))},
        })

        snapshots[safe_key] = snapshots[safe_key][-30:]

        snapshot_file.write_text(
            json.dumps(snapshots, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load_recent_snapshots(self) -> dict:
        trends = {}
        snapshot_dir = self.business_path / "_snapshots"
        for snap_file in snapshot_dir.glob("*.json"):
            try:
                data = json.loads(snap_file.read_text(encoding="utf-8"))
                for key, entries in data.items():
                    for entry in entries[-7:]:
                        for metric, val in entry.get("data", {}).items():
                            if isinstance(val, (int, float)):
                                trend_key = f"{key}.{metric}"
                                if trend_key not in trends:
                                    trends[trend_key] = []
                                trends[trend_key].append(val)
            except (json.JSONDecodeError, OSError):
                continue
        return trends

    def _safe_filename(self, name: str) -> str:
        import re
        sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
        sanitized = re.sub(r"\s+", "_", sanitized)
        return sanitized.strip("_.")[:100] or "untitled"

    def _avoid_overwrite(self, filepath: Path) -> Path:
        if not filepath.exists():
            return filepath
        counter = 1
        stem = filepath.stem
        while filepath.exists():
            filepath = filepath.parent / f"{stem}_{counter}{filepath.suffix}"
            counter += 1
        return filepath

    def _format_metric_label(self, key: str) -> str:
        label_map = {
            "revenue": "Doanh thu",
            "profit": "Lợi nhuận",
            "costs": "Chi phí",
            "orders": "Số đơn",
            "customers": "Khách hàng",
            "close_rate": "Tỷ lệ chốt",
            "spend": "Chi phí quảng cáo",
            "impressions": "Lượt hiển thị",
            "clicks": "Lượt click",
            "conversions": "Chuyển đổi",
            "ctr": "CTR",
            "cpc": "CPC",
            "cpa": "CPA",
            "roas": "ROAS",
            "market_cap": "Vốn hóa",
            "pe_ratio": "P/E",
            "eps": "EPS",
            "price": "Giá",
            "volume": "Khối lượng",
        }
        return label_map.get(key.lower(), key.replace("_", " ").title())

    def _format_number(self, val) -> str:
        if not isinstance(val, (int, float)):
            return str(val)
        if abs(val) >= 1_000_000_000:
            return f"{val / 1_000_000_000:.1f}B"
        if abs(val) >= 1_000_000:
            return f"{val / 1_000_000:.1f}M"
        if abs(val) >= 1_000:
            return f"{val / 1_000:.1f}K"
        if isinstance(val, float):
            return f"{val:.2f}"
        return str(val)

    def _calc_change(self, current, previous) -> float:
        if previous == 0:
            return 0.0
        try:
            return ((float(current) - float(previous)) / float(previous)) * 100
        except (ValueError, TypeError):
            return 0.0

    def _vn_key(self, key: str) -> str:
        mapping = {
            "revenue": "doanh_thu",
            "profit": "loi_nhuan",
            "costs": "chi_phi",
            "orders": "don_hang",
            "customers": "khach_hang",
            "close_rate": "ty_le_chot",
        }
        return mapping.get(key, key)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DX Business Data Collector")
    parser.add_argument(
        "--vault", default=os.environ.get("OBSIDIAN_VAULT_PATH", "/home/user/ObsidianVault")
    )
    parser.add_argument("--type", choices=["market", "marketing", "finance", "competitor", "report"])
    parser.add_argument("--data", help="JSON data string or file path")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    collector = BusinessCollector(args.vault)

    if args.stats:
        stats = collector.get_business_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        sys.exit(0)

    if not args.data or not args.type:
        parser.print_help()
        sys.exit(1)

    raw = args.data
    if len(raw) < 260 and not raw.strip().startswith("{"):
        data_path = Path(raw)
        if data_path.exists():
            raw = data_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    type_handlers = {
        "market": collector.process_market_intel,
        "marketing": collector.process_marketing_analytics,
        "finance": collector.process_finance_snapshot,
        "competitor": collector.process_competitor_intel,
        "report": collector.generate_daily_report,
    }

    handler = type_handlers[args.type]
    if args.type == "report":
        path = handler(data)
    else:
        path = handler(data, source=args.source)

    print(json.dumps({"written": str(path)}, ensure_ascii=False))

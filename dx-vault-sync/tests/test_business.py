#!/usr/bin/env python3
"""
DX Vault Sync — Phase 2 Test Suite
Validates business data collection, processing, and vault writing.
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from business_collector import BusinessCollector
from business_loop import BusinessLoop


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  \033[32m PASS\033[0m {name}")

    def fail(self, name: str, reason: str):
        self.failed += 1
        self.errors.append(f"{name}: {reason}")
        print(f"  \033[31m FAIL\033[0m {name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        color = "\033[32m" if self.failed == 0 else "\033[31m"
        print(f"\n{color}Results: {self.passed}/{total} passed\033[0m")
        return self.failed == 0


def test_business_collector(t: TestResult):
    print("\n--- BusinessCollector ---")
    tmp_dir = tempfile.mkdtemp(prefix="dx-biz-test-")

    try:
        collector = BusinessCollector(tmp_dir)

        biz_path = Path(tmp_dir) / "DX-Memory" / "business"
        expected_dirs = ["market-intel", "marketing-analytics", "finance-snapshots",
                         "alerts", "competitors", "reports", "_snapshots"]
        missing = [d for d in expected_dirs if not (biz_path / d).is_dir()]
        if not missing:
            t.ok("create business directories")
        else:
            t.fail("create business directories", f"missing: {missing}")

        market_data = {
            "company_name": "Test Corp",
            "metrics": {"market_cap": 1000000000, "pe_ratio": 20.5, "eps": 5.2, "price": 105.0},
            "sentiment": {"score": 75, "trend": "improving", "summary": "Positive outlook"},
            "events": [{"date": "2026-07-01", "title": "Earnings Call"}],
            "raw_summary": "Test Corp shows strong performance.",
        }
        path = collector.process_market_intel(market_data, source="test")
        if path.exists():
            content = path.read_text(encoding="utf-8")
            checks = ["market-intel" in content, "Test Corp" in content, "1.0B" in content or "1000000000" in content]
            if all(checks):
                t.ok("process market intel")
            else:
                t.fail("process market intel", f"missing content in {path.name}")
        else:
            t.fail("process market intel", "file not created")

        marketing_data = {
            "platform": "Google Ads",
            "period": "2026-06",
            "totals": {"spend": 15000, "impressions": 850000, "clicks": 42500,
                       "conversions": 1275, "revenue": 63750, "ctr": 5.0, "roas": 4.25},
            "campaigns": [
                {"name": "Campaign A", "spend": 8000, "clicks": 25000, "conversions": 750, "roas": 4.5},
                {"name": "Campaign B", "spend": 7000, "clicks": 17500, "conversions": 525, "roas": 4.0},
            ],
        }
        path = collector.process_marketing_analytics(marketing_data, source="test")
        if path.exists():
            content = path.read_text(encoding="utf-8")
            checks = ["Google Ads" in content, "Campaign A" in content, "ROAS" in content]
            if all(checks):
                t.ok("process marketing analytics")
            else:
                t.fail("process marketing analytics", "missing content")
        else:
            t.fail("process marketing analytics", "file not created")

        finance_data = {
            "entity": "DX Advisory",
            "period": "2026-06",
            "revenue": 201900000,
            "costs": 138300000,
            "profit": 63600000,
            "orders": 500,
            "customers": 356,
            "close_rate": 93.63,
            "previous_period": {
                "revenue": 377800000,
                "profit": 99400000,
                "orders": 916,
                "customers": 689,
            },
            "notes": "Seasonal adjustment",
            "action_items": ["Review strategy", "Optimize retention"],
        }
        path = collector.process_finance_snapshot(finance_data, source="test")
        if path.exists():
            content = path.read_text(encoding="utf-8")
            checks = ["DX Advisory" in content, "201.9M" in content, "Doanh thu" in content]
            if all(checks):
                t.ok("process finance snapshot")
            else:
                t.fail("process finance snapshot", f"missing content")
        else:
            t.fail("process finance snapshot", "file not created")

        alert_dir = biz_path / "alerts"
        alert_files = list(alert_dir.glob("*.md"))
        if len(alert_files) > 0:
            alert_content = alert_files[0].read_text(encoding="utf-8")
            if "giảm" in alert_content or "tăng" in alert_content:
                t.ok("auto-detect anomalies and create alerts")
            else:
                t.fail("auto-detect anomalies", "alert content missing trend direction")
        else:
            t.fail("auto-detect anomalies", "no alert files created")

        competitor_data = {
            "name": "Competitor X",
            "overview": "Leading player in the market",
            "strengths": ["Strong brand", "Large market share"],
            "weaknesses": ["Slow innovation", "High prices"],
            "recent_moves": ["Launched new product line", "Expanded to new market"],
            "metrics": {"market_share": "25%", "revenue_growth": "12%"},
        }
        path = collector.process_competitor_intel(competitor_data, source="test")
        if path.exists():
            content = path.read_text(encoding="utf-8")
            if "Competitor X" in content and "Điểm mạnh" in content:
                t.ok("process competitor intel")
            else:
                t.fail("process competitor intel", "missing content")
        else:
            t.fail("process competitor intel", "file not created")

        report_data = {
            "finance": {"revenue": 201900000, "profit": 63600000, "orders": 500},
            "marketing": {"spend": 15000, "roas": 4.25, "conversions": 1275},
            "market": ["Positive outlook", "AI adoption accelerating"],
            "alerts": ["Revenue decreased"],
            "action_items": ["Review strategy"],
        }
        path = collector.generate_daily_report(report_data)
        if path.exists() and "reports" in str(path):
            t.ok("generate daily report")
        else:
            t.fail("generate daily report", f"path: {path}")

        stats = collector.get_business_stats()
        if stats["total_notes"] >= 5:
            t.ok(f"business stats ({stats['total_notes']} notes)")
        else:
            t.fail("business stats", f"expected >=5, got {stats['total_notes']}")

        snapshot_file = biz_path / "_snapshots" / "market-intel.json"
        if snapshot_file.exists():
            snap_data = json.loads(snapshot_file.read_text(encoding="utf-8"))
            if len(snap_data) > 0:
                t.ok("save data snapshots for trends")
            else:
                t.fail("save snapshots", "empty snapshot data")
        else:
            t.fail("save snapshots", "snapshot file not created")

        dup_path = collector.process_market_intel(market_data, source="test")
        if dup_path.exists() and dup_path != path:
            t.ok("handle duplicate filenames")
        else:
            t.fail("handle duplicates", "same path or not created")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_business_loop(t: TestResult):
    print("\n--- BusinessLoop ---")
    tmp_dir = tempfile.mkdtemp(prefix="dx-biz-test-")

    try:
        loop = BusinessLoop(tmp_dir)

        tasks = loop.list_tasks()
        expected_keys = {"market-scan", "marketing-pull", "news-scan", "finance-snapshot", "daily-report"}
        actual_keys = {task["key"] for task in tasks}
        if expected_keys == actual_keys:
            t.ok(f"list tasks ({len(tasks)} available)")
        else:
            t.fail("list tasks", f"expected {expected_keys}, got {actual_keys}")

        prompt = loop.generate_prompt("market-scan", entity="Test Corp")
        if "find_securities" in prompt and "Test Corp" in prompt:
            t.ok("generate market-scan prompt")
        else:
            t.fail("generate market-scan prompt", "missing MCP tool references")

        prompt = loop.generate_prompt("marketing-pull")
        if "data_source_discovery" in prompt and "data_query" in prompt:
            t.ok("generate marketing-pull prompt")
        else:
            t.fail("generate marketing-pull prompt", "missing Supermetrics tools")

        prompt = loop.generate_prompt("finance-snapshot", entity="DX Advisory")
        if "DX Advisory" in prompt and "Doanh thu" in prompt:
            t.ok("generate finance-snapshot prompt")
        else:
            t.fail("generate finance-snapshot prompt", "missing content")

        full_loop = loop.generate_full_loop(
            entities=["DX Advisory", "Competitor X"],
            tasks=["market-scan", "finance-snapshot"],
        )
        if "DX Advisory" in full_loop and "Competitor X" in full_loop and "Step 1" in full_loop:
            t.ok("generate full loop")
        else:
            t.fail("generate full loop", "missing entities or steps")

        status = loop.get_status()
        if "vault_path" in status and "available_tasks" in status:
            t.ok("loop status")
        else:
            t.fail("loop status", f"missing keys: {status.keys()}")

        bad_prompt = loop.generate_prompt("nonexistent-task")
        if "Unknown task" in bad_prompt:
            t.ok("handle unknown task gracefully")
        else:
            t.fail("handle unknown task", f"got: {bad_prompt[:50]}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_number_formatting(t: TestResult):
    print("\n--- Number Formatting ---")
    tmp_dir = tempfile.mkdtemp(prefix="dx-biz-test-")

    try:
        collector = BusinessCollector(tmp_dir)

        cases = [
            (1500000000, "1.5B"),
            (201900000, "201.9M"),
            (15000, "15.0K"),
            (93.63, "93.63"),
            (500, "500"),
        ]

        all_ok = True
        for val, expected in cases:
            result = collector._format_number(val)
            if result != expected:
                t.fail(f"format {val}", f"expected '{expected}', got '{result}'")
                all_ok = False

        if all_ok:
            t.ok(f"number formatting ({len(cases)} cases)")

        change = collector._calc_change(201900000, 377800000)
        if -47 < change < -46:
            t.ok(f"calculate change ({change:.1f}%)")
        else:
            t.fail("calculate change", f"expected ~-46.6%, got {change:.1f}%")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    t = TestResult()

    print("=" * 50)
    print("DX Vault Sync — Phase 2 Business Test Suite")
    print("=" * 50)

    test_business_collector(t)
    test_business_loop(t)
    test_number_formatting(t)

    success = t.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

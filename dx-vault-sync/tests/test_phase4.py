#!/usr/bin/env python3
"""
DX Vault Sync — Phase 4 Test Suite
Tests: Knowledge Gap Detector, Auto-Research, Weekly Digest, Memo Bridge, API endpoints.
"""

import sys
import json
import tempfile
import shutil
import os
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))


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
        if self.errors:
            print("Failures:")
            for e in self.errors:
                print(f"  - {e}")
        return self.failed == 0


def setup_test_vault(tmp_dir: str):
    """Create a test vault with sample data for gap detection."""
    from vault_writer import VaultWriter
    from sync_engine import SyncEngine
    from business_collector import BusinessCollector

    engine = SyncEngine(tmp_dir)
    engine.sync_text(
        "Quyết định dùng FastAPI cho API server. "
        "Cần làm: viết unit tests cho Phase 4. "
        "Học được rằng gap detection cần scan toàn bộ vault.",
        source="test",
    )

    collector = BusinessCollector(tmp_dir)
    collector.process_finance_snapshot({
        "entity": "Test Corp",
        "period": "2026-06",
        "revenue": 100000000,
        "profit": 30000000,
        "orders": 250,
    }, source="test")

    collector.process_marketing_analytics({
        "platform": "Google Ads",
        "period": "2026-06",
        "totals": {"spend": 5000, "clicks": 10000, "conversions": 300, "roas": 3.5},
    }, source="test")


def test_gap_detector(t: TestResult, tmp_dir: str):
    print("\n--- Gap Detector ---")
    from gap_detector import GapDetector

    detector = GapDetector(tmp_dir)

    try:
        result = detector.full_scan()
        if isinstance(result, dict) and "gaps" in result:
            t.ok(f"full_scan() — {result['total_notes']} notes scanned")
        else:
            t.fail("full_scan()", f"unexpected result type: {type(result)}")
    except Exception as e:
        t.fail("full_scan()", str(e))

    try:
        result = detector.scan_and_score()
        score = result.get("health_score", -1)
        if 0 <= score <= 100:
            t.ok(f"scan_and_score() — health: {score}/100")
        else:
            t.fail("scan_and_score()", f"invalid score: {score}")
    except Exception as e:
        t.fail("scan_and_score()", str(e))

    try:
        report = detector.generate_gap_report()
        if "Vault Health Report" in report and "Health score" in report:
            t.ok(f"generate_gap_report() — {len(report)} chars")
        else:
            t.fail("generate_gap_report()", "missing expected content")
    except Exception as e:
        t.fail("generate_gap_report()", str(e))

    try:
        prompts = detector.get_research_prompts(max_prompts=3)
        if isinstance(prompts, list):
            t.ok(f"get_research_prompts() — {len(prompts)} prompts")
        else:
            t.fail("get_research_prompts()", f"expected list, got {type(prompts)}")
    except Exception as e:
        t.fail("get_research_prompts()", str(e))

    try:
        scan = detector.scan_and_score()
        gaps = scan["gaps"]
        expected_keys = ["stale_notes", "orphan_notes", "empty_categories",
                         "broken_links", "missing_tags", "open_tasks",
                         "topic_gaps", "data_freshness"]
        missing = [k for k in expected_keys if k not in gaps]
        if not missing:
            t.ok("gap categories — all 8 present")
        else:
            t.fail("gap categories", f"missing: {missing}")
    except Exception as e:
        t.fail("gap categories", str(e))

    try:
        freshness = scan["gaps"]["data_freshness"]
        if isinstance(freshness, list) and len(freshness) > 0:
            t.ok(f"data_freshness — {len(freshness)} categories checked")
        else:
            t.fail("data_freshness", "empty or not a list")
    except Exception as e:
        t.fail("data_freshness", str(e))

    try:
        recs = scan.get("recommendations", [])
        if isinstance(recs, list):
            t.ok(f"recommendations — {len(recs)} items")
        else:
            t.fail("recommendations", f"expected list, got {type(recs)}")
    except Exception as e:
        t.fail("recommendations", str(e))


def test_auto_research(t: TestResult, tmp_dir: str):
    print("\n--- Auto-Research Engine ---")
    from auto_research import AutoResearch

    researcher = AutoResearch(tmp_dir)

    try:
        plan = researcher.analyze_and_plan(max_items=5)
        if isinstance(plan, dict) and "research_items" in plan:
            t.ok(f"analyze_and_plan() — {len(plan['research_items'])} items, health: {plan['health_score']}")
        else:
            t.fail("analyze_and_plan()", "missing research_items")
    except Exception as e:
        t.fail("analyze_and_plan()", str(e))

    try:
        prompt = researcher.generate_claude_prompt()
        if isinstance(prompt, str) and len(prompt) > 0:
            t.ok(f"generate_claude_prompt() — {len(prompt)} chars")
        else:
            t.fail("generate_claude_prompt()", "empty prompt")
    except Exception as e:
        t.fail("generate_claude_prompt()", str(e))

    try:
        script = researcher.generate_loop_script()
        if isinstance(script, str) and len(script) > 0:
            t.ok(f"generate_loop_script() — {len(script)} chars")
        else:
            t.fail("generate_loop_script()", "empty script")
    except Exception as e:
        t.fail("generate_loop_script()", str(e))

    try:
        path = researcher.store_research_result(
            "Test Topic",
            "Test findings: FastAPI is great for building REST APIs.",
            "test",
        )
        if path.exists():
            t.ok(f"store_research_result() — {path.name}")
        else:
            t.fail("store_research_result()", "file not created")
    except Exception as e:
        t.fail("store_research_result()", str(e))

    try:
        history = researcher.get_research_history()
        if isinstance(history, list) and len(history) >= 1:
            t.ok(f"get_research_history() — {len(history)} entries")
        else:
            t.fail("get_research_history()", f"expected >=1, got {len(history)}")
    except Exception as e:
        t.fail("get_research_history()", str(e))


def test_weekly_digest(t: TestResult, tmp_dir: str):
    print("\n--- Weekly Digest ---")
    from weekly_digest import WeeklyDigest

    digest = WeeklyDigest(tmp_dir)

    try:
        result = digest.generate(days=7, save=False)
        if isinstance(result, dict) and "summary" in result and "period" in result:
            t.ok(f"generate(7d) — {result['summary']['new_notes']} notes in period")
        else:
            t.fail("generate()", "missing expected keys")
    except Exception as e:
        t.fail("generate()", str(e))

    try:
        md = digest.generate_markdown(days=7)
        if "Weekly Digest" in md and "Tổng quan" in md:
            t.ok(f"generate_markdown() — {len(md)} chars")
        else:
            t.fail("generate_markdown()", "missing expected content")
    except Exception as e:
        t.fail("generate_markdown()", str(e))

    try:
        result = digest.generate(days=7, save=True)
        saved = result.get("saved_path", "")
        if saved and Path(saved).exists():
            t.ok(f"save digest — {Path(saved).name}")
        else:
            t.fail("save digest", f"path: {saved}")
    except Exception as e:
        t.fail("save digest", str(e))

    try:
        result = digest.generate(days=30, save=False)
        cats = result.get("categories", {})
        if isinstance(cats, dict):
            t.ok(f"30-day digest — {sum(cats.values())} notes across {len(cats)} categories")
        else:
            t.fail("30-day digest", "categories not dict")
    except Exception as e:
        t.fail("30-day digest", str(e))

    try:
        biz = result.get("business", {})
        if isinstance(biz, dict):
            t.ok(f"business summary — has_data: {biz.get('has_data', False)}")
        else:
            t.fail("business summary", "not dict")
    except Exception as e:
        t.fail("business summary", str(e))


def test_memo_bridge(t: TestResult, tmp_dir: str):
    print("\n--- Memo Bridge ---")
    from memo_bridge import MemoBridge

    bridge = MemoBridge(tmp_dir)

    try:
        md = bridge.generate_claude_md()
        if "DX Vault" in md and "Vault Health" in md:
            t.ok(f"generate_claude_md() — {len(md)} chars")
        else:
            t.fail("generate_claude_md()", "missing expected sections")
    except Exception as e:
        t.fail("generate_claude_md()", str(e))

    try:
        output_file = Path(tmp_dir) / "test_claude.md"
        bridge.generate_claude_md(str(output_file))
        if output_file.exists():
            t.ok(f"generate_claude_md(file) — written to {output_file.name}")
        else:
            t.fail("generate_claude_md(file)", "file not created")
    except Exception as e:
        t.fail("generate_claude_md(file)", str(e))

    try:
        ctx = bridge.inject_session_context()
        if "Session Context" in ctx:
            t.ok(f"inject_session_context() — {len(ctx)} chars")
        else:
            t.fail("inject_session_context()", "missing expected content")
    except Exception as e:
        t.fail("inject_session_context()", str(e))

    try:
        result = bridge.auto_loop_tick()
        if isinstance(result, dict) and "actions" in result:
            t.ok(f"auto_loop_tick() — {len(result['actions'])} actions")
        else:
            t.fail("auto_loop_tick()", "missing actions")
    except Exception as e:
        t.fail("auto_loop_tick()", str(e))

    try:
        status = bridge.get_full_status()
        expected = ["stats", "health_score", "gap_summary", "recommendations"]
        missing = [k for k in expected if k not in status]
        if not missing:
            t.ok(f"get_full_status() — health: {status['health_score']}/100")
        else:
            t.fail("get_full_status()", f"missing: {missing}")
    except Exception as e:
        t.fail("get_full_status()", str(e))

    try:
        export = bridge.export_for_jarvis()
        if export.get("platform") == "jarvis" and "context_summary" in export:
            t.ok(f"export_for_jarvis() — {len(export['open_tasks'])} tasks, {len(export['recent_decisions'])} decisions")
        else:
            t.fail("export_for_jarvis()", "missing expected fields")
    except Exception as e:
        t.fail("export_for_jarvis()", str(e))


def test_api_endpoints(t: TestResult, tmp_dir: str):
    print("\n--- Phase 4 API Endpoints ---")

    os.environ["OBSIDIAN_VAULT_PATH"] = tmp_dir
    os.environ["DX_VAULT_API_KEY"] = ""

    import importlib
    import server as server_module
    importlib.reload(server_module)

    server_module.VAULT_PATH = tmp_dir
    server_module.API_KEY = ""
    server_module.engine = server_module.SyncEngine(tmp_dir, "DX-Memory")
    server_module.collector = server_module.BusinessCollector(tmp_dir, "DX-Memory")
    server_module.loader = server_module.ContextLoader(tmp_dir, "DX-Memory")
    server_module.gap_detector = server_module.GapDetector(tmp_dir, "DX-Memory")
    server_module.auto_researcher = server_module.AutoResearch(tmp_dir, "DX-Memory")
    server_module.digest_gen = server_module.WeeklyDigest(tmp_dir, "DX-Memory")
    server_module.memo_bridge = server_module.MemoBridge(tmp_dir, "DX-Memory")

    from fastapi.testclient import TestClient
    client = TestClient(server_module.app)

    r = client.get("/api/vault/gaps")
    if r.status_code == 200 and "health_score" in r.json():
        t.ok(f"GET /api/vault/gaps — health: {r.json()['health_score']}")
    else:
        t.fail("GET /api/vault/gaps", f"{r.status_code}: {r.text[:100]}")

    r = client.get("/api/vault/gaps/report")
    if r.status_code == 200 and "report" in r.json():
        t.ok(f"GET /api/vault/gaps/report — {len(r.json()['report'])} chars")
    else:
        t.fail("GET /api/vault/gaps/report", f"{r.status_code}")

    r = client.get("/api/vault/research")
    if r.status_code == 200 and "research_items" in r.json():
        t.ok(f"GET /api/vault/research — {len(r.json()['research_items'])} items")
    else:
        t.fail("GET /api/vault/research", f"{r.status_code}")

    r = client.post("/api/vault/research/store", params={
        "topic": "API Test Research",
        "findings": "Testing the research store endpoint works correctly.",
        "source": "test",
    })
    if r.status_code == 200 and "stored" in r.json():
        t.ok("POST /api/vault/research/store")
    else:
        t.fail("POST /api/vault/research/store", f"{r.status_code}: {r.text[:100]}")

    r = client.get("/api/vault/digest", params={"days": 7})
    if r.status_code == 200 and "digest" in r.json():
        t.ok(f"GET /api/vault/digest — {len(r.json()['digest'])} chars")
    else:
        t.fail("GET /api/vault/digest", f"{r.status_code}")

    r = client.get("/api/vault/memo/status")
    if r.status_code == 200 and "health_score" in r.json():
        t.ok(f"GET /api/vault/memo/status — health: {r.json()['health_score']}")
    else:
        t.fail("GET /api/vault/memo/status", f"{r.status_code}")

    r = client.post("/api/vault/memo/tick")
    if r.status_code == 200 and "actions" in r.json():
        t.ok(f"POST /api/vault/memo/tick — {len(r.json()['actions'])} actions")
    else:
        t.fail("POST /api/vault/memo/tick", f"{r.status_code}")

    r = client.get("/openapi.json")
    if r.status_code == 200:
        paths = list(r.json().get("paths", {}).keys())
        phase4_paths = [p for p in paths if "gaps" in p or "research" in p or "digest" in p or "memo" in p]
        if len(phase4_paths) >= 5:
            t.ok(f"OpenAPI spec — {len(phase4_paths)} Phase 4 endpoints")
        else:
            t.fail("OpenAPI spec", f"only {len(phase4_paths)} Phase 4 paths")
    else:
        t.fail("OpenAPI spec", f"{r.status_code}")


def run_tests():
    tmp_dir = tempfile.mkdtemp(prefix="dx-phase4-test-")

    try:
        setup_test_vault(tmp_dir)
        t = TestResult()

        test_gap_detector(t, tmp_dir)
        test_auto_research(t, tmp_dir)
        test_weekly_digest(t, tmp_dir)
        test_memo_bridge(t, tmp_dir)
        test_api_endpoints(t, tmp_dir)

        return t.summary()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    print("=" * 50)
    print("DX Vault Sync — Phase 4 Test Suite")
    print("=" * 50)

    success = run_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

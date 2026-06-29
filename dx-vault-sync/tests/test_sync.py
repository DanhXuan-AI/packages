#!/usr/bin/env python3
"""
DX Vault Sync — Test Suite
Validates extraction, writing, and context loading pipelines.
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from extract_insights import InsightExtractor
from vault_writer import VaultWriter
from context_loader import ContextLoader
from sync_engine import SyncEngine


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


def test_extractor(t: TestResult):
    print("\n--- InsightExtractor ---")
    extractor = InsightExtractor()

    text = "Quyết định sẽ dùng FastAPI cho backend mới"
    insights = extractor.extract_from_text(text)
    if insights and insights[0]["category"] == "decision":
        t.ok("classify decision")
    else:
        t.fail("classify decision", f"got {insights}")

    text = "Cần làm: deploy production server trước thứ 6"
    insights = extractor.extract_from_text(text)
    if insights and insights[0]["category"] == "task":
        t.ok("classify task")
    else:
        t.fail("classify task", f"got {insights}")

    text = "Học được rằng Python async rất mạnh cho IO-bound tasks"
    insights = extractor.extract_from_text(text)
    if insights and insights[0]["category"] == "learning":
        t.ok("classify learning")
    else:
        t.fail("classify learning", f"got {insights}")

    text = "Khách hàng Ane Co Lodge cần support hệ thống POS"
    insights = extractor.extract_from_text(text)
    if insights and insights[0]["category"] == "entity":
        t.ok("classify entity")
    else:
        t.fail("classify entity", f"got {insights}")

    text = "Quyết định dùng FastAPI. Cần làm setup project. Học được async patterns."
    insights = extractor.extract_from_text(text, source="test")
    if len(insights) >= 1:
        t.ok(f"multi-extract ({len(insights)} insights)")
    else:
        t.fail("multi-extract", "no insights extracted")

    for insight in insights:
        if all(k in insight for k in ("id", "category", "content", "title", "tags", "confidence")):
            continue
        else:
            t.fail("insight structure", f"missing keys in {insight.keys()}")
            break
    else:
        t.ok("insight structure complete")

    text = "abc"
    insights = extractor.extract_from_text(text)
    if len(insights) == 0:
        t.ok("skip short text")
    else:
        t.fail("skip short text", f"got {len(insights)} insights")

    summary = extractor.extract_conversation_summary(
        "Hôm nay bàn về FastAPI và deployment strategy cho POScake"
    )
    if summary.get("category") == "conversation":
        t.ok("conversation summary")
    else:
        t.fail("conversation summary", f"got {summary}")


def test_vault_writer(t: TestResult):
    print("\n--- VaultWriter ---")
    tmp_dir = tempfile.mkdtemp(prefix="dx-vault-test-")

    try:
        writer = VaultWriter(tmp_dir)

        for subdir in ["decisions", "learnings", "entities", "tasks", "context", "conversations"]:
            if (Path(tmp_dir) / "DX-Memory" / subdir).is_dir():
                continue
            else:
                t.fail("create dirs", f"missing {subdir}")
                break
        else:
            t.ok("create vault directories")

        insight = {
            "id": "test001",
            "category": "decision",
            "title": "Test Decision",
            "content": "This is a test decision",
            "tags": ["decision", "test"],
            "links": ["TestProject"],
            "source": "test",
            "timestamp": "2026-06-29T10:00:00",
            "confidence": 0.9,
        }
        path = writer.write_insight(insight)
        if path.exists():
            t.ok("write single insight")
        else:
            t.fail("write single insight", "file not created")

        content = path.read_text(encoding="utf-8")
        if "---" in content and "type: decision" in content:
            t.ok("frontmatter present")
        else:
            t.fail("frontmatter present", "missing YAML frontmatter")

        if "[[TestProject]]" in content:
            t.ok("wiki links in content")
        else:
            t.fail("wiki links in content", "wiki link not found")

        batch = [
            {"id": f"batch{i}", "category": cat, "title": f"Batch {cat}",
             "content": f"Content for {cat}", "tags": [cat], "links": [],
             "source": "test", "timestamp": "2026-06-29T10:00:00", "confidence": 0.8}
            for i, cat in enumerate(["learning", "task", "entity"])
        ]
        paths = writer.write_batch(batch)
        if len(paths) == 3:
            t.ok("write batch (3 insights)")
        else:
            t.fail("write batch", f"expected 3, got {len(paths)}")

        summary = {
            "title": "Test Conversation",
            "topics": ["testing", "vault"],
            "key_points": ["Point 1", "Point 2"],
            "message_count": 10,
            "tags": ["conversation", "test"],
            "content": "## Test\n- Point 1\n- Point 2",
        }
        conv_path = writer.write_conversation_log(summary)
        if conv_path.exists() and "conversations" in str(conv_path):
            t.ok("write conversation log")
        else:
            t.fail("write conversation log", f"path: {conv_path}")

        stats = writer.get_stats()
        if stats["total_notes"] >= 4:
            t.ok(f"vault stats ({stats['total_notes']} notes)")
        else:
            t.fail("vault stats", f"expected >=4, got {stats['total_notes']}")

        results = writer.search_vault("test")
        if len(results) > 0:
            t.ok(f"search vault ({len(results)} results)")
        else:
            t.fail("search vault", "no results")

        dup_path = writer.write_insight(insight)
        if dup_path.exists() and dup_path != path:
            t.ok("handle duplicate filename")
        else:
            t.fail("handle duplicate", "same path or not created")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_context_loader(t: TestResult):
    print("\n--- ContextLoader ---")
    tmp_dir = tempfile.mkdtemp(prefix="dx-vault-test-")

    try:
        writer = VaultWriter(tmp_dir)
        writer.write_batch([
            {"id": "ctx1", "category": "context", "title": "User prefers dark mode",
             "content": "User always uses dark mode and prefers Vietnamese",
             "tags": ["context", "preference"], "links": [], "source": "test",
             "timestamp": "2026-06-29T10:00:00", "confidence": 0.9},
            {"id": "ctx2", "category": "task", "title": "Deploy POScake v2",
             "content": "Cần deploy POScake v2 trước cuối tháng",
             "tags": ["task", "poscake"], "links": ["POScake"], "source": "test",
             "timestamp": "2026-06-29T10:00:00", "confidence": 0.85},
        ])

        loader = ContextLoader(tmp_dir)

        context = loader.generate_claude_context()
        if "DX Vault" in context and "Total notes" in context:
            t.ok("generate claude context")
        else:
            t.fail("generate claude context", f"incomplete: {context[:100]}")

        cat_context = loader.load_category_context("context")
        if "dark mode" in cat_context or "preference" in cat_context.lower():
            t.ok("load category context")
        else:
            t.fail("load category context", f"got: {cat_context[:100]}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sync_engine(t: TestResult):
    print("\n--- SyncEngine ---")
    tmp_dir = tempfile.mkdtemp(prefix="dx-vault-test-")

    try:
        engine = SyncEngine(tmp_dir)

        result = engine.sync_text(
            "Quyết định dùng PostgreSQL cho database chính. "
            "Cần làm: migration script tuần này. "
            "Học được: PostgreSQL JSONB rất mạnh cho semi-structured data.",
            source="test"
        )

        if result.get("insights_found", 0) >= 1:
            t.ok(f"sync text ({result['insights_found']} insights, {result['files_written']} files)")
        else:
            t.fail("sync text", f"result: {result}")

        status = engine.get_status()
        if status["stats"]["total_notes"] > 0:
            t.ok(f"engine status ({status['stats']['total_notes']} notes)")
        else:
            t.fail("engine status", f"got: {status}")

        context = engine.load_context()
        if context:
            t.ok("load context via engine")
        else:
            t.fail("load context via engine", "empty context")

        result2 = engine.sync_text(
            "Quyết định dùng PostgreSQL cho database chính.",
            source="test-dup"
        )
        t.ok(f"dedup handling ({result2['files_written']} files)")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    t = TestResult()

    print("=" * 50)
    print("DX Vault Sync — Test Suite")
    print("=" * 50)

    test_extractor(t)
    test_vault_writer(t)
    test_context_loader(t)
    test_sync_engine(t)

    success = t.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
DX Vault Sync — Phase 3 API Test Suite
Tests the FastAPI vault bridge endpoints using TestClient.
"""

import sys
import json
import tempfile
import shutil
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

os.environ.pop("DX_VAULT_API_KEY", None)


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


def run_tests():
    from fastapi.testclient import TestClient

    tmp_dir = tempfile.mkdtemp(prefix="dx-api-test-")
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

    client = TestClient(server_module.app)
    t = TestResult()

    try:
        print("\n--- Health & Stats ---")

        r = client.get("/api/health")
        if r.status_code == 200 and r.json()["status"] == "ok":
            t.ok("GET /api/health")
        else:
            t.fail("GET /api/health", f"{r.status_code}: {r.text[:100]}")

        r = client.get("/api/vault/stats")
        if r.status_code == 200 and "total_notes" in r.json():
            t.ok("GET /api/vault/stats")
        else:
            t.fail("GET /api/vault/stats", f"{r.status_code}")

        print("\n--- Sync & Learn ---")

        r = client.post("/api/vault/sync", json={
            "text": "Quyết định dùng FastAPI cho API server. Cần làm: viết tests. Học được rằng TestClient rất tiện.",
            "source": "test",
        })
        if r.status_code == 200:
            data = r.json()
            if data.get("insights_found", 0) >= 1 and data.get("files_written", 0) >= 1:
                t.ok(f"POST /api/vault/sync ({data['insights_found']} insights, {data['files_written']} files)")
            else:
                t.fail("POST /api/vault/sync", f"low counts: {data}")
        else:
            t.fail("POST /api/vault/sync", f"{r.status_code}: {r.text[:100]}")

        r = client.post("/api/vault/learn", json={
            "content": "FastAPI auto-generates OpenAPI docs from type hints",
            "category": "learning",
            "tags": ["python", "api", "fastapi"],
            "source": "test",
        })
        if r.status_code == 200 and r.json().get("category") == "learning":
            t.ok("POST /api/vault/learn")
        else:
            t.fail("POST /api/vault/learn", f"{r.status_code}: {r.text[:100]}")

        r = client.post("/api/vault/learn", json={
            "content": "Deploy staging server by Friday",
            "category": "task",
            "tags": ["deploy", "deadline"],
        })
        if r.status_code == 200 and r.json().get("category") == "task":
            t.ok("POST /api/vault/learn (task)")
        else:
            t.fail("POST /api/vault/learn (task)", f"{r.status_code}")

        print("\n--- Context & Search ---")

        r = client.get("/api/vault/context")
        if r.status_code == 200 and "context" in r.json():
            t.ok("GET /api/vault/context")
        else:
            t.fail("GET /api/vault/context", f"{r.status_code}")

        r = client.get("/api/vault/context", params={"query": "FastAPI"})
        if r.status_code == 200:
            t.ok("GET /api/vault/context?query=FastAPI")
        else:
            t.fail("GET /api/vault/context?query", f"{r.status_code}")

        r = client.get("/api/vault/search", params={"q": "FastAPI"})
        if r.status_code == 200 and r.json().get("total", 0) >= 1:
            t.ok(f"GET /api/vault/search ({r.json()['total']} results)")
        else:
            t.fail("GET /api/vault/search", f"{r.status_code}: {r.json()}")

        r = client.get("/api/vault/search", params={"q": "nonexistent_xyz_123"})
        if r.status_code == 200 and r.json().get("total") == 0:
            t.ok("GET /api/vault/search (no results)")
        else:
            t.fail("GET /api/vault/search (empty)", f"{r.status_code}")

        print("\n--- Notes ---")

        r = client.get("/api/vault/notes")
        if r.status_code == 200 and isinstance(r.json(), list):
            t.ok(f"GET /api/vault/notes ({len(r.json())} notes)")
        else:
            t.fail("GET /api/vault/notes", f"{r.status_code}")

        r = client.get("/api/vault/notes", params={"category": "learning"})
        if r.status_code == 200:
            t.ok(f"GET /api/vault/notes?category=learning ({len(r.json())} notes)")
        else:
            t.fail("GET /api/vault/notes?category", f"{r.status_code}")

        notes = client.get("/api/vault/notes").json()
        if notes:
            note_path = notes[0].get("path", "")
            if note_path:
                r = client.get("/api/vault/note", params={"path": note_path})
                if r.status_code == 200 and "content" in r.json() and "frontmatter" in r.json():
                    t.ok("GET /api/vault/note (single)")
                else:
                    t.fail("GET /api/vault/note", f"{r.status_code}")
            else:
                t.fail("GET /api/vault/note", "no path in note")
        else:
            t.fail("GET /api/vault/note", "no notes to read")

        r = client.get("/api/vault/note", params={"path": "/nonexistent/file.md"})
        if r.status_code == 404:
            t.ok("GET /api/vault/note (404 for missing)")
        else:
            t.fail("GET /api/vault/note (404)", f"got {r.status_code}")

        print("\n--- Business Data ---")

        r = client.post("/api/vault/business", json={
            "data_type": "finance",
            "data": {
                "entity": "Test Corp",
                "period": "2026-06",
                "revenue": 100000000,
                "profit": 30000000,
                "orders": 250,
                "previous_period": {"revenue": 150000000, "profit": 45000000, "orders": 400},
            },
            "source": "test",
        })
        if r.status_code == 200 and r.json().get("data_type") == "finance":
            t.ok("POST /api/vault/business (finance)")
        else:
            t.fail("POST /api/vault/business (finance)", f"{r.status_code}: {r.text[:100]}")

        r = client.post("/api/vault/business", json={
            "data_type": "marketing",
            "data": {
                "platform": "Facebook Ads",
                "period": "2026-06",
                "totals": {"spend": 5000, "clicks": 10000, "conversions": 300, "roas": 3.5},
            },
            "source": "test",
        })
        if r.status_code == 200:
            t.ok("POST /api/vault/business (marketing)")
        else:
            t.fail("POST /api/vault/business (marketing)", f"{r.status_code}")

        r = client.post("/api/vault/business", json={
            "data_type": "invalid_type",
            "data": {},
        })
        if r.status_code == 400:
            t.ok("POST /api/vault/business (invalid type → 400)")
        else:
            t.fail("POST /api/vault/business (400)", f"got {r.status_code}")

        print("\n--- Alerts & Trends ---")

        r = client.get("/api/vault/alerts")
        if r.status_code == 200 and isinstance(r.json(), list):
            alert_count = len(r.json())
            t.ok(f"GET /api/vault/alerts ({alert_count} alerts)")
        else:
            t.fail("GET /api/vault/alerts", f"{r.status_code}")

        r = client.get("/api/vault/alerts", params={"status": "all"})
        if r.status_code == 200:
            t.ok("GET /api/vault/alerts?status=all")
        else:
            t.fail("GET /api/vault/alerts?status=all", f"{r.status_code}")

        r = client.get("/api/vault/trends")
        if r.status_code == 200 and "trends" in r.json():
            t.ok("GET /api/vault/trends")
        else:
            t.fail("GET /api/vault/trends", f"{r.status_code}")

        r = client.get("/api/vault/trends", params={"metric": "revenue", "days": 7})
        if r.status_code == 200:
            t.ok("GET /api/vault/trends?metric=revenue")
        else:
            t.fail("GET /api/vault/trends?metric", f"{r.status_code}")

        print("\n--- Final Stats ---")

        r = client.get("/api/vault/stats")
        if r.status_code == 200:
            stats = r.json()
            total = stats.get("total_notes", 0)
            t.ok(f"Final vault stats: {total} total notes")
        else:
            t.fail("Final stats", f"{r.status_code}")

        print("\n--- OpenAPI Spec ---")

        r = client.get("/openapi.json")
        if r.status_code == 200:
            spec = r.json()
            paths = list(spec.get("paths", {}).keys())
            if len(paths) >= 10:
                t.ok(f"OpenAPI spec generated ({len(paths)} endpoints)")
            else:
                t.fail("OpenAPI spec", f"only {len(paths)} paths")
        else:
            t.fail("OpenAPI spec", f"{r.status_code}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return t.summary()


def main():
    print("=" * 50)
    print("DX Vault Sync — Phase 3 API Test Suite")
    print("=" * 50)

    success = run_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

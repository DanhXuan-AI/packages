#!/usr/bin/env python3
"""
DX Vault Sync — Phase 3: Vault API Server
RESTful API bridge between ChatGPT Custom GPTs and Obsidian Vault.

Endpoints:
  GET  /api/vault/context       — Load active context summary
  GET  /api/vault/search        — Search vault notes
  GET  /api/vault/notes         — List notes by category
  GET  /api/vault/note          — Read a single note
  GET  /api/vault/stats         — Vault statistics
  GET  /api/vault/alerts        — Unread business alerts
  GET  /api/vault/trends        — Business trend data
  POST /api/vault/sync          — Sync text content to vault
  POST /api/vault/business      — Sync business data to vault
  POST /api/vault/learn         — Store a learning/insight
  GET  /api/health              — Health check
  GET  /openapi.json            — OpenAPI spec (for ChatGPT Actions)

Auth: Bearer token via X-API-Key header.
"""

import os
import sys
import json
import secrets
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from sync_engine import SyncEngine
from business_collector import BusinessCollector
from vault_writer import VaultWriter
from context_loader import ContextLoader

VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", "/home/user/ObsidianVault")
API_KEY = os.environ.get("DX_VAULT_API_KEY", "")
MEMORY_DIR = "DX-Memory"

app = FastAPI(
    title="DX Vault Sync API",
    description=(
        "API bridge between ChatGPT Custom GPTs and Obsidian Vault (Second Brain). "
        "Enables reading context, syncing conversations, and managing business data "
        "across Claude Code, ChatGPT, and Jarvis OS."
    ),
    version="1.0.0",
    servers=[
        {"url": os.environ.get("DX_VAULT_API_URL", "http://localhost:8900")},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = SyncEngine(VAULT_PATH, MEMORY_DIR)
collector = BusinessCollector(VAULT_PATH, MEMORY_DIR)
loader = ContextLoader(VAULT_PATH, MEMORY_DIR)


def verify_api_key(x_api_key: str = Header(default="")):
    if not API_KEY:
        return True
    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


# --- Request/Response Models ---

class SyncRequest(BaseModel):
    text: str = Field(..., description="Text content to extract insights from and sync to vault")
    source: str = Field(default="chatgpt", description="Source platform identifier")

class SyncResponse(BaseModel):
    timestamp: str
    source: str
    insights_found: int
    files_written: int
    paths: list[str]
    categories: dict[str, int]
    conversation_title: str

class BusinessDataRequest(BaseModel):
    data_type: str = Field(..., description="Type: market, marketing, finance, competitor, report")
    data: dict = Field(..., description="Structured business data payload")
    source: str = Field(default="chatgpt", description="Data source identifier")

class BusinessDataResponse(BaseModel):
    written: str
    data_type: str
    timestamp: str

class LearnRequest(BaseModel):
    content: str = Field(..., description="What was learned or decided")
    category: str = Field(
        default="learning",
        description="Category: learning, decision, task, entity, context",
    )
    tags: list[str] = Field(default_factory=list, description="Additional tags")
    source: str = Field(default="chatgpt", description="Source platform")

class LearnResponse(BaseModel):
    id: str
    category: str
    title: str
    path: str
    timestamp: str

class NoteOut(BaseModel):
    filename: str
    category: str
    created: str
    tags: list[str]
    content_preview: str
    path: str

class SearchResult(BaseModel):
    results: list[NoteOut]
    query: str
    total: int

class VaultStats(BaseModel):
    total_notes: int
    categories: dict
    last_sync: Optional[str] = None
    business_stats: Optional[dict] = None

class AlertOut(BaseModel):
    filename: str
    severity: str
    entity: str
    period: str
    alerts: list[str]
    status: str
    created: str


# --- Endpoints ---

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "vault_path": VAULT_PATH,
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    }


@app.get("/api/vault/context", response_model=dict)
async def get_context(
    query: str = Query(default="", description="Search query to find relevant context"),
    category: str = Query(default="", description="Filter by category"),
    hours: int = Query(default=24, description="Hours of recent context to load"),
    _auth: bool = Depends(verify_api_key),
):
    """Load active context from Obsidian Vault.
    Returns a structured summary of recent decisions, open tasks, and preferences.
    ChatGPT should call this at the start of each conversation to load user context."""
    if query:
        context_text = loader.load_relevant_context(query)
    elif category:
        context_text = loader.load_category_context(category)
    else:
        context_text = loader.generate_claude_context()

    return {
        "context": context_text,
        "query": query,
        "category": category,
        "loaded_at": datetime.now().isoformat(),
    }


@app.get("/api/vault/search", response_model=SearchResult)
async def search_vault(
    q: str = Query(..., description="Search query"),
    limit: int = Query(default=10, ge=1, le=50, description="Max results"),
    _auth: bool = Depends(verify_api_key),
):
    """Search across all vault notes. Returns matching notes with content preview."""
    writer = VaultWriter(VAULT_PATH, MEMORY_DIR)
    results = writer.search_vault(q, limit=limit)

    notes = []
    for r in results:
        fm = r.get("frontmatter", {})
        notes.append(NoteOut(
            filename=r.get("filename", ""),
            category=fm.get("type", r.get("category", "unknown")),
            created=fm.get("created", r.get("created", "")),
            tags=fm.get("tags", r.get("tags", [])),
            content_preview=r.get("content", "")[:300],
            path=r.get("path", ""),
        ))

    return SearchResult(results=notes, query=q, total=len(notes))


@app.get("/api/vault/notes", response_model=list[NoteOut])
async def list_notes(
    category: str = Query(
        default="",
        description="Filter: decision, learning, task, entity, context, conversation, "
        "market-intel, marketing-analytics, finance-snapshots, alerts, competitors, reports",
    ),
    limit: int = Query(default=10, ge=1, le=50),
    _auth: bool = Depends(verify_api_key),
):
    """List vault notes, optionally filtered by category."""
    writer = VaultWriter(VAULT_PATH, MEMORY_DIR)

    if category in ("market-intel", "marketing-analytics", "finance-snapshots",
                     "alerts", "competitors", "reports"):
        biz_dir = Path(VAULT_PATH) / MEMORY_DIR / "business" / category
        notes = []
        if biz_dir.exists():
            for md_file in sorted(biz_dir.glob("*.md"), key=os.path.getmtime, reverse=True)[:limit]:
                parsed = writer._parse_vault_note(md_file)
                if parsed:
                    fm = parsed.get("frontmatter", {})
                    notes.append(NoteOut(
                        filename=parsed["filename"],
                        category=fm.get("type", category),
                        created=fm.get("created", ""),
                        tags=fm.get("tags", []),
                        content_preview=parsed.get("content", "")[:300],
                        path=str(md_file),
                    ))
        return notes

    results = writer.read_context(category=category or None, limit=limit)
    return [
        NoteOut(
            filename=r.get("filename", ""),
            category=r.get("frontmatter", {}).get("type", r.get("category", "")),
            created=r.get("created", ""),
            tags=r.get("tags", []),
            content_preview=r.get("content", "")[:300],
            path=r.get("path", ""),
        )
        for r in results
    ]


@app.get("/api/vault/note", response_model=dict)
async def read_note(
    path: str = Query(..., description="Full path to the note file"),
    _auth: bool = Depends(verify_api_key),
):
    """Read a specific vault note with full content and frontmatter."""
    note_path = Path(path)
    if not note_path.exists():
        raise HTTPException(status_code=404, detail="Note not found")

    vault_base = Path(VAULT_PATH).resolve()
    if not note_path.resolve().is_relative_to(vault_base):
        raise HTTPException(status_code=403, detail="Access denied — path outside vault")

    writer = VaultWriter(VAULT_PATH, MEMORY_DIR)
    parsed = writer._parse_vault_note(note_path)
    if not parsed:
        raise HTTPException(status_code=500, detail="Failed to parse note")

    return {
        "filename": parsed["filename"],
        "frontmatter": parsed["frontmatter"],
        "content": parsed["content"],
        "path": str(note_path),
    }


@app.get("/api/vault/stats", response_model=VaultStats)
async def vault_stats(_auth: bool = Depends(verify_api_key)):
    """Get vault statistics including note counts per category and business data stats."""
    writer = VaultWriter(VAULT_PATH, MEMORY_DIR)
    stats = writer.get_stats()
    biz_stats = collector.get_business_stats()

    return VaultStats(
        total_notes=stats["total_notes"] + biz_stats["total_notes"],
        categories={**stats.get("categories", {}), **{
            f"business/{k}": v["count"]
            for k, v in biz_stats.get("categories", {}).items()
        }},
        last_sync=stats.get("last_sync"),
        business_stats=biz_stats,
    )


@app.get("/api/vault/alerts", response_model=list[AlertOut])
async def get_alerts(
    status: str = Query(default="unread", description="Filter: unread, all"),
    limit: int = Query(default=20, ge=1, le=100),
    _auth: bool = Depends(verify_api_key),
):
    """Get business alerts from the vault. Defaults to unread alerts only."""
    import yaml as yaml_lib

    alerts_dir = Path(VAULT_PATH) / MEMORY_DIR / "business" / "alerts"
    results = []

    if not alerts_dir.exists():
        return results

    for md_file in sorted(alerts_dir.glob("*.md"), key=os.path.getmtime, reverse=True)[:limit]:
        try:
            text = md_file.read_text(encoding="utf-8")
            import re
            fm_match = re.match(r"^---\s*\n(.+?)\n---\s*\n(.*)$", text, re.DOTALL)
            if not fm_match:
                continue
            fm = yaml_lib.safe_load(fm_match.group(1)) or {}
            content = fm_match.group(2)

            if status == "unread" and fm.get("status") != "unread":
                continue

            alert_lines = [
                line.strip().lstrip("- ").lstrip("⚠️ ").strip()
                for line in content.split("\n")
                if line.strip().startswith("- ⚠️") or line.strip().startswith("-  ⚠️")
            ]

            results.append(AlertOut(
                filename=md_file.stem,
                severity=fm.get("severity", "warning"),
                entity=fm.get("entity", ""),
                period=fm.get("period", ""),
                alerts=alert_lines,
                status=fm.get("status", "unread"),
                created=fm.get("created", ""),
            ))
        except (yaml_lib.YAMLError, OSError):
            continue

    return results


@app.get("/api/vault/trends", response_model=dict)
async def get_trends(
    metric: str = Query(default="", description="Specific metric to get trend for"),
    days: int = Query(default=7, ge=1, le=30),
    _auth: bool = Depends(verify_api_key),
):
    """Get business trend data from stored snapshots."""
    snapshots_dir = Path(VAULT_PATH) / MEMORY_DIR / "business" / "_snapshots"
    trends = {}

    if not snapshots_dir.exists():
        return {"trends": {}, "days": days}

    for snap_file in snapshots_dir.glob("*.json"):
        try:
            data = json.loads(snap_file.read_text(encoding="utf-8"))
            for key, entries in data.items():
                for entry in entries[-days:]:
                    for m, val in entry.get("data", {}).items():
                        if isinstance(val, (int, float)):
                            if metric and metric.lower() not in m.lower():
                                continue
                            trend_key = f"{key}.{m}"
                            if trend_key not in trends:
                                trends[trend_key] = []
                            trends[trend_key].append({
                                "timestamp": entry.get("timestamp", ""),
                                "value": val,
                            })
        except (json.JSONDecodeError, OSError):
            continue

    return {"trends": trends, "days": days, "metric_filter": metric}


@app.post("/api/vault/sync", response_model=SyncResponse)
async def sync_content(
    req: SyncRequest,
    _auth: bool = Depends(verify_api_key),
):
    """Sync text content to the vault. Automatically extracts insights
    (decisions, learnings, tasks, entities) and creates Obsidian notes.
    ChatGPT should call this to save important conversation content."""
    result = engine.sync_text(req.text, source=req.source)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return SyncResponse(**result)


@app.post("/api/vault/business", response_model=BusinessDataResponse)
async def sync_business_data(
    req: BusinessDataRequest,
    _auth: bool = Depends(verify_api_key),
):
    """Sync structured business data to the vault.
    Supports: market intel, marketing analytics, finance snapshots,
    competitor intel, and daily reports."""
    handlers = {
        "market": collector.process_market_intel,
        "marketing": collector.process_marketing_analytics,
        "finance": collector.process_finance_snapshot,
        "competitor": collector.process_competitor_intel,
        "report": collector.generate_daily_report,
    }

    if req.data_type not in handlers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid data_type: {req.data_type}. Must be one of: {list(handlers.keys())}",
        )

    handler = handlers[req.data_type]
    if req.data_type == "report":
        path = handler(req.data)
    else:
        path = handler(req.data, source=req.source)

    return BusinessDataResponse(
        written=str(path),
        data_type=req.data_type,
        timestamp=datetime.now().isoformat(),
    )


@app.post("/api/vault/learn", response_model=LearnResponse)
async def learn_insight(
    req: LearnRequest,
    _auth: bool = Depends(verify_api_key),
):
    """Store a specific learning, decision, or task directly.
    More targeted than /sync — use when you know the exact category."""
    from extract_insights import InsightExtractor

    extractor = InsightExtractor()
    content_hash = hashlib.md5(req.content.strip().lower().encode()).hexdigest()[:12]

    insight = {
        "id": content_hash,
        "category": req.category,
        "content": req.content,
        "title": req.content.split("\n")[0][:80],
        "tags": [req.category] + req.tags,
        "links": [],
        "source": req.source,
        "timestamp": datetime.now().isoformat(),
        "confidence": 0.9,
    }

    writer = VaultWriter(VAULT_PATH, MEMORY_DIR)
    path = writer.write_insight(insight)

    return LearnResponse(
        id=content_hash,
        category=req.category,
        title=insight["title"],
        path=str(path),
        timestamp=datetime.now().isoformat(),
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DX_VAULT_API_PORT", "8900"))
    print(f"Starting DX Vault API on port {port}...")
    print(f"Vault: {VAULT_PATH}")
    print(f"OpenAPI docs: http://localhost:{port}/docs")
    print(f"ChatGPT Actions spec: http://localhost:{port}/openapi.json")
    uvicorn.run(app, host="0.0.0.0", port=port)

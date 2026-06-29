#!/usr/bin/env python3
"""
DX Vault Sync — Main Sync Engine
Orchestrates the full sync pipeline:
  conversation → extract → classify → write → index → report
"""

import json
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extract_insights import InsightExtractor
from vault_writer import VaultWriter
from context_loader import ContextLoader


class SyncEngine:
    def __init__(self, vault_path: str, memory_dir: str = "DX-Memory"):
        self.vault_path = Path(vault_path).expanduser()
        self.memory_dir = memory_dir
        self.extractor = InsightExtractor()
        self.writer = VaultWriter(str(self.vault_path), memory_dir)
        self.loader = ContextLoader(str(self.vault_path), memory_dir)
        self.sync_log: list[dict] = []

    def sync_text(self, text: str, source: str = "manual") -> dict:
        insights = self.extractor.extract_from_text(text, source=source)
        summary = self.extractor.extract_conversation_summary(text)

        written_paths = []

        if insights:
            paths = self.writer.write_batch(insights)
            written_paths.extend(paths)

        conv_path = self.writer.write_conversation_log(summary)
        written_paths.append(conv_path)

        result = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "insights_found": len(insights),
            "files_written": len(written_paths),
            "paths": [str(p) for p in written_paths],
            "categories": self._count_categories(insights),
            "conversation_title": summary.get("title", ""),
        }

        self._log_sync(result)
        return result

    def sync_file(self, filepath: str, source: str = "file") -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"error": f"File not found: {filepath}"}

        text = path.read_text(encoding="utf-8")
        return self.sync_text(text, source=source or path.stem)

    def sync_session(self, session_path: str) -> dict:
        path = Path(session_path)
        if not path.exists():
            return {"error": f"Session directory not found: {session_path}"}

        insights = self.extractor.extract_from_session(session_path)

        all_text = []
        for jsonl_file in sorted(path.glob("*.jsonl")):
            try:
                all_text.append(jsonl_file.read_text(encoding="utf-8"))
            except OSError:
                continue

        combined_text = "\n".join(all_text)
        summary = self.extractor.extract_conversation_summary(combined_text)

        written_paths = []
        if insights:
            paths = self.writer.write_batch(insights)
            written_paths.extend(paths)

        conv_path = self.writer.write_conversation_log(summary)
        written_paths.append(conv_path)

        result = {
            "timestamp": datetime.now().isoformat(),
            "source": f"session:{path.name}",
            "insights_found": len(insights),
            "files_written": len(written_paths),
            "paths": [str(p) for p in written_paths],
            "categories": self._count_categories(insights),
            "conversation_title": summary.get("title", ""),
        }

        self._log_sync(result)
        return result

    def sync_clipboard(self) -> dict:
        try:
            import subprocess

            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return self.sync_text(result.stdout, source="clipboard")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            import subprocess

            result = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return self.sync_text(result.stdout, source="clipboard")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return {"error": "Could not read clipboard"}

    def load_context(self, query: str = "", category: str = "") -> str:
        if query:
            return self.loader.load_relevant_context(query)
        if category:
            return self.loader.load_category_context(category)
        return self.loader.generate_claude_context()

    def get_status(self) -> dict:
        stats = self.writer.get_stats()
        return {
            "vault_path": str(self.vault_path),
            "memory_dir": self.memory_dir,
            "stats": stats,
            "session_syncs": len(self.sync_log),
        }

    def _count_categories(self, insights: list[dict]) -> dict:
        counts: dict[str, int] = {}
        for i in insights:
            cat = i.get("category", "unknown")
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def _log_sync(self, result: dict):
        self.sync_log.append(result)


def main():
    parser = argparse.ArgumentParser(
        description="DX Vault Sync — Sync conversations to Obsidian Vault",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s sync --text "Quyết định dùng FastAPI cho dự án mới"
  %(prog)s sync --file conversation.md
  %(prog)s sync --session ~/.claude/sessions/abc123
  %(prog)s context --query "FastAPI"
  %(prog)s context --category decision
  %(prog)s status
        """,
    )

    parser.add_argument(
        "--vault",
        default=os.environ.get("OBSIDIAN_VAULT_PATH", "/tmp/dx-vault-demo"),
        help="Path to Obsidian vault",
    )
    parser.add_argument(
        "--memory-dir", default="DX-Memory", help="Memory subdirectory name"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    sync_parser = subparsers.add_parser("sync", help="Sync content to vault")
    sync_group = sync_parser.add_mutually_exclusive_group(required=True)
    sync_group.add_argument("--text", help="Text to sync")
    sync_group.add_argument("--file", help="File to sync")
    sync_group.add_argument("--session", help="Claude session directory to sync")
    sync_group.add_argument(
        "--clipboard", action="store_true", help="Sync from clipboard"
    )
    sync_parser.add_argument("--source", default="", help="Source label")

    ctx_parser = subparsers.add_parser("context", help="Load context from vault")
    ctx_parser.add_argument("--query", default="", help="Search query")
    ctx_parser.add_argument("--category", default="", help="Category filter")
    ctx_parser.add_argument("--output", default="", help="Output file path")

    subparsers.add_parser("status", help="Show vault status")

    args = parser.parse_args()
    engine = SyncEngine(args.vault, args.memory_dir)

    if args.command == "sync":
        if args.text:
            result = engine.sync_text(args.text, source=args.source or "cli")
        elif args.file:
            result = engine.sync_file(args.file, source=args.source)
        elif args.session:
            result = engine.sync_session(args.session)
        elif args.clipboard:
            result = engine.sync_clipboard()
        else:
            result = {"error": "No input specified"}

        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "context":
        context = engine.load_context(query=args.query, category=args.category)
        if args.output:
            Path(args.output).write_text(context, encoding="utf-8")
            print(f"Context written to {args.output}")
        else:
            print(context)

    elif args.command == "status":
        status = engine.get_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

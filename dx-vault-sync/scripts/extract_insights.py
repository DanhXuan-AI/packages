#!/usr/bin/env python3
"""
DX Vault Sync — Conversation Insight Extractor
Extracts structured insights from Claude Code conversation transcripts
and classifies them for Obsidian Vault storage.
"""

import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional


CATEGORY_PATTERNS = {
    "decision": [
        r"quyết định|quyết_định|decide|decision|chọn|chọn phương án|lựa chọn",
        r"sẽ dùng|sẽ sử dụng|will use|going with|let'?s go with",
        r"approve|phê duyệt|đồng ý với|agreed on",
    ],
    "learning": [
        r"học được|learned|insight|nhận ra|realize|hiểu rồi|understood",
        r"hóa ra|turns out|TIL|mẹo|trick|tip|best practice",
        r"lưu ý|note that|quan trọng|important|key takeaway",
    ],
    "entity": [
        r"khách hàng|client|customer|công ty|company|dự án|project",
        r"đối tác|partner|nhà cung cấp|vendor|sản phẩm|product",
        r"nhân viên|employee|team|đội ngũ",
    ],
    "task": [
        r"cần làm|todo|to-do|task|việc cần|action item",
        r"follow[- ]?up|theo dõi|nhắc nhở|remind|deadline",
        r"triển khai|implement|deploy|chạy thử|test",
    ],
    "context": [
        r"thói quen|habit|preference|sở thích|phong cách|style",
        r"luôn luôn|always|không bao giờ|never|thường|usually",
        r"cách .+ thích|prefer|workflow|quy trình",
    ],
}


class InsightExtractor:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.dedup_hashes: set[str] = set()

    def extract_from_text(self, text: str, source: str = "claude-code") -> list[dict]:
        chunks = self._split_into_chunks(text)
        insights = []

        for chunk in chunks:
            category = self._classify(chunk)
            if not category:
                continue

            content_hash = hashlib.md5(chunk.strip().lower().encode()).hexdigest()[:12]
            if content_hash in self.dedup_hashes:
                continue
            self.dedup_hashes.add(content_hash)

            insight = {
                "id": content_hash,
                "category": category,
                "content": chunk.strip(),
                "title": self._generate_title(chunk, category),
                "tags": self._extract_tags(chunk, category),
                "links": self._extract_wiki_links(chunk),
                "source": source,
                "timestamp": datetime.now().isoformat(),
                "confidence": self._calculate_confidence(chunk, category),
            }
            insights.append(insight)

        return insights

    def extract_from_session(self, session_path: str) -> list[dict]:
        path = Path(session_path)
        if not path.exists():
            return []

        all_insights = []

        for jsonl_file in sorted(path.glob("*.jsonl")):
            try:
                messages = self._parse_jsonl(jsonl_file)
                conversation_text = self._messages_to_text(messages)
                insights = self.extract_from_text(
                    conversation_text, source=f"claude-code:{jsonl_file.stem}"
                )
                all_insights.extend(insights)
            except (json.JSONDecodeError, KeyError):
                continue

        return all_insights

    def extract_conversation_summary(self, text: str) -> dict:
        lines = text.strip().split("\n")
        non_empty = [l for l in lines if l.strip()]

        topics = self._extract_topics(text)
        key_points = self._extract_key_points(text)

        return {
            "category": "conversation",
            "title": self._generate_conversation_title(topics),
            "topics": topics,
            "key_points": key_points,
            "message_count": len(non_empty),
            "tags": ["conversation"] + topics[:5],
            "timestamp": datetime.now().isoformat(),
            "content": self._build_summary_content(topics, key_points),
        }

    def _split_into_chunks(self, text: str) -> list[str]:
        paragraphs = re.split(r"\n{2,}", text)
        chunks = []
        current_chunk = []

        for para in paragraphs:
            current_chunk.append(para)
            if len("\n".join(current_chunk)) > 200:
                chunks.append("\n".join(current_chunk))
                current_chunk = []

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return [c for c in chunks if len(c.strip()) > 30]

    def _classify(self, text: str) -> Optional[str]:
        scores: dict[str, int] = {}
        text_lower = text.lower()

        for category, patterns in CATEGORY_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, text_lower)
                score += len(matches)
            if score > 0:
                scores[category] = score

        if not scores:
            return None

        return max(scores, key=scores.get)

    def _generate_title(self, text: str, category: str) -> str:
        first_line = text.strip().split("\n")[0]
        first_line = re.sub(r"[#*`>\-]", "", first_line).strip()

        if len(first_line) > 80:
            first_line = first_line[:77] + "..."

        if not first_line:
            prefix_map = {
                "decision": "Quyết định",
                "learning": "Kiến thức",
                "entity": "Thực thể",
                "task": "Công việc",
                "context": "Ngữ cảnh",
            }
            first_line = f"{prefix_map.get(category, 'Note')} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        return first_line

    def _extract_tags(self, text: str, category: str) -> list[str]:
        tags = [category]
        text_lower = text.lower()

        tech_tags = {
            "python": r"\bpython\b",
            "javascript": r"\bjavascript\b|\bjs\b|\bnode\b",
            "api": r"\bapi\b|\bendpoint\b|\brest\b",
            "database": r"\bdatabase\b|\bdb\b|\bsql\b|\bmongodb\b",
            "devops": r"\bdocker\b|\bci/?cd\b|\bdeploy\b",
            "ai": r"\bai\b|\bllm\b|\bclaude\b|\bgpt\b|\bmodel\b",
            "mcp": r"\bmcp\b",
            "obsidian": r"\bobsidian\b|\bvault\b",
            "business": r"\bdoanh thu\b|\blợi nhuận\b|\bkhách hàng\b|\bsales\b",
            "marketing": r"\bmarketing\b|\bads\b|\bquảng cáo\b|\bfacebook\b",
        }

        for tag, pattern in tech_tags.items():
            if re.search(pattern, text_lower):
                tags.append(tag)

        return list(dict.fromkeys(tags))

    def _extract_wiki_links(self, text: str) -> list[str]:
        links = re.findall(r"\[\[([^\]]+)\]\]", text)
        return links

    def _calculate_confidence(self, text: str, category: str) -> float:
        score = 0.5
        if len(text) > 100:
            score += 0.1
        if len(text) > 300:
            score += 0.1

        text_lower = text.lower()
        strong_signals = sum(
            1
            for pattern in CATEGORY_PATTERNS.get(category, [])
            if re.search(pattern, text_lower)
        )
        score += min(strong_signals * 0.1, 0.3)

        return min(score, 1.0)

    def _extract_topics(self, text: str) -> list[str]:
        topic_patterns = [
            r"(?:về|about|regarding)\s+(.+?)(?:\.|,|\n|$)",
            r"(?:chủ đề|topic|subject):\s*(.+?)(?:\.|,|\n|$)",
        ]
        topics = []
        for pattern in topic_patterns:
            matches = re.findall(pattern, text.lower())
            topics.extend(m.strip() for m in matches if len(m.strip()) > 3)

        if not topics:
            words = re.findall(r"\b[A-Z][a-zA-Z]{3,}\b", text)
            topics = list(dict.fromkeys(words))[:5]

        return topics[:10]

    def _extract_key_points(self, text: str) -> list[str]:
        points = []

        bullet_points = re.findall(r"[-*]\s+(.+)", text)
        points.extend(bp.strip() for bp in bullet_points[:10])

        numbered = re.findall(r"\d+[.)]\s+(.+)", text)
        points.extend(n.strip() for n in numbered[:10])

        return points[:15]

    def _generate_conversation_title(self, topics: list[str]) -> str:
        if topics:
            main_topics = ", ".join(topics[:3])
            return f"Session - {main_topics}"
        return f"Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    def _build_summary_content(self, topics: list[str], key_points: list[str]) -> str:
        parts = []
        if topics:
            parts.append("## Chủ đề chính\n" + "\n".join(f"- {t}" for t in topics))
        if key_points:
            parts.append(
                "## Điểm quan trọng\n" + "\n".join(f"- {p}" for p in key_points)
            )
        return "\n\n".join(parts) if parts else "Không có nội dung đáng chú ý."

    def _parse_jsonl(self, path: Path) -> list[dict]:
        messages = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return messages

    def _messages_to_text(self, messages: list[dict]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    c.get("text", "") for c in content if isinstance(c, dict)
                ]
                content = "\n".join(text_parts)
            if content and role in ("user", "assistant"):
                parts.append(f"[{role}]\n{content}")
        return "\n\n".join(parts)


if __name__ == "__main__":
    import sys

    extractor = InsightExtractor()

    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if input_path.is_dir():
            insights = extractor.extract_from_session(str(input_path))
        else:
            text = input_path.read_text(encoding="utf-8")
            insights = extractor.extract_from_text(text)

        print(json.dumps(insights, ensure_ascii=False, indent=2))
    else:
        sample = """
        Hôm nay quyết định sẽ dùng FastAPI cho backend của dự án POScake v2.
        Lý do: hiệu năng cao hơn Flask, hỗ trợ async tốt.
        Cần làm: setup project structure, viết API endpoints cho orders.
        Học được: FastAPI tự generate OpenAPI docs, rất tiện cho team frontend.
        """
        insights = extractor.extract_from_text(sample, source="demo")
        print(json.dumps(insights, ensure_ascii=False, indent=2))

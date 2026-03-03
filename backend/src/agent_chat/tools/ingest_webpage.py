"""Web page ingestion tool — fetches a URL and saves content to the knowledge base."""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup

from agent_chat.services.kb_service import ingest_webpage_to_kb
from agent_chat.tools.base import Tool

logger = structlog.get_logger()

_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 200


def _extract_text(html: str) -> tuple[str, str]:
    """Extract readable text and title from HTML.

    Returns (title, body_text).
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    # Extract title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Prefer <article> or <main>, fall back to <body>
    content_el = soup.find("article") or soup.find("main") or soup.body
    if not content_el:
        return title, ""

    text = content_el.get_text(separator="\n", strip=True)
    return title, text


def _split_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap

    return chunks


class IngestWebpageTool(Tool):
    name = "ingest_webpage"
    description = "抓取网页内容并保存到知识库，之后可以通过 kb_search 检索。用于保存文章、文档等网页信息。"
    risk_level = "write"
    timeout_seconds = 30.0
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "网页 URL",
            },
            "title": {
                "type": "string",
                "description": "自定义标题（可选，不填则自动从网页提取）",
            },
        },
        "required": ["url"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        user_id = (context or {}).get("user_id")
        if not user_id:
            return {"error": "User context required", "code": "NO_USER_CONTEXT"}

        url = arguments["url"]
        custom_title = arguments.get("title")

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 AgentChat/1.0"})
                resp.raise_for_status()
        except httpx.HTTPError as e:
            return {"error": f"Failed to fetch URL: {e}", "code": "FETCH_ERROR"}

        html = resp.text
        extracted_title, body_text = _extract_text(html)
        title = custom_title or extracted_title or url

        if not body_text.strip():
            return {"error": "No readable content found on page", "code": "EMPTY_CONTENT"}

        chunks = _split_text(body_text)
        count = await ingest_webpage_to_kb(user_id, url, title, chunks)

        return {
            "url": url,
            "title": title,
            "chunks_saved": count,
            "message": f"已保存 {count} 个文本片段到知识库",
        }

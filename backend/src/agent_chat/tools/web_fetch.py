"""Web fetch tool — fetches a URL and returns readable text content to the LLM."""

from __future__ import annotations

import os
import ssl
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup

from agent_chat.tools.base import Tool

logger = structlog.get_logger()

_MAX_CONTENT_LENGTH = 4000  # chars returned to LLM


def _extract_text(html: str) -> tuple[str, str]:
    """Extract readable text and title from HTML."""
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    content_el = soup.find("article") or soup.find("main") or soup.body
    if not content_el:
        return title, ""

    text = content_el.get_text(separator="\n", strip=True)
    return title, text


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "抓取网页内容并直接返回正文文本。用于在搜索后深入阅读某个链接的详细内容。"
    risk_level = "read"
    timeout_seconds = 20.0
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要抓取的网页 URL",
            },
        },
        "required": ["url"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = arguments.get("url", "").strip()
        if not url:
            return {"error": "Missing url parameter"}

        try:
            proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.load_default_certs()
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, proxy=proxy, verify=ssl_ctx
            ) as client:
                resp = await client.get(
                    url, headers={"User-Agent": "Mozilla/5.0 AgentChat/1.0"}
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("web_fetch_error", url=url, error=str(e))
            return {"error": f"无法访问该网页（{type(e).__name__}）"}

        title, body_text = _extract_text(resp.text)

        if not body_text.strip():
            return {"url": url, "title": title, "content": "", "note": "未能提取到正文内容"}

        truncated = len(body_text) > _MAX_CONTENT_LENGTH
        content = body_text[:_MAX_CONTENT_LENGTH]

        return {
            "url": url,
            "title": title or url,
            "content": content,
            "truncated": truncated,
            "char_count": len(body_text),
        }

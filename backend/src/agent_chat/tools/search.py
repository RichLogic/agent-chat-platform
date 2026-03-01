"""Search tool — SerpAPI (primary) with Brave Search fallback."""

from __future__ import annotations

import os
import ssl
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from agent_chat.config import get_settings
from agent_chat.tools.base import Tool

logger = structlog.get_logger()


class SearchTool(Tool):
    name = "search"
    description = "搜索互联网获取最新信息。当用户询问事件详情、最新进展、或需要事实核查时使用。结果包含来源链接。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "num": {
                "type": "integer",
                "description": "结果数量，1-10，默认 5",
            },
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query", "").strip()
        if not query:
            return {"error": "Missing query parameter"}

        num = min(max(int(arguments.get("num", 5)), 1), 10)
        settings = get_settings()

        # Try SerpAPI first
        if settings.serpapi_key:
            try:
                result = await self._search_serpapi(query, num, settings.serpapi_key)
                if "error" not in result:
                    return result
                logger.warning("serpapi_failed", query=query, error=result["error"])
            except httpx.HTTPError as e:
                logger.warning("serpapi_http_error", query=query, error=str(e))

        # Fallback to Brave Search
        if settings.brave_search_key:
            try:
                result = await self._search_brave(query, num, settings.brave_search_key)
                if "error" not in result:
                    return result
                logger.warning("brave_failed", query=query, error=result["error"])
            except httpx.HTTPError as e:
                logger.warning("brave_http_error", query=query, error=str(e))

        return {"error": "搜索服务暂时不可用，请稍后再试"}

    def _make_client(self, timeout: float = 10.0) -> httpx.AsyncClient:
        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.load_default_certs()
        return httpx.AsyncClient(timeout=timeout, proxy=proxy, verify=ssl_ctx)

    async def _search_serpapi(
        self, query: str, num: int, api_key: str
    ) -> dict[str, Any]:
        async with self._make_client() as client:
            resp = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": api_key,
                    "engine": "google",
                    "num": num,
                    "hl": "zh-cn",
                },
            )
            if resp.status_code == 429:
                return {"error": "SerpAPI rate limited"}
            data = resp.json()

        if "error" in data:
            return {"error": f"SerpAPI: {data['error']}"}

        organic = data.get("organic_results", [])[:num]
        results = []
        for item in organic:
            url = item.get("link", "")
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "url": url,
                "source": urlparse(url).netloc if url else "",
            })

        return {"query": query, "engine": "serpapi", "results": results}

    async def _search_brave(
        self, query: str, num: int, api_key: str
    ) -> dict[str, Any]:
        async with self._make_client() as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": api_key},
                params={"q": query, "count": num},
            )
            if resp.status_code == 429:
                return {"error": "Brave rate limited"}
            data = resp.json()

        web_results = data.get("web", {}).get("results", [])[:num]
        if not web_results:
            return {"query": query, "engine": "brave", "results": []}

        results = []
        for item in web_results:
            url = item.get("url", "")
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("description", ""),
                "url": url,
                "source": urlparse(url).netloc if url else "",
            })

        return {"query": query, "engine": "brave", "results": results}

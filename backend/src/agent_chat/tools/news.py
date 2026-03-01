"""News tool — queries NewsAPI.org for top headlines."""

from __future__ import annotations

import os
import ssl
from typing import Any

import httpx
import structlog

from agent_chat.config import get_settings
from agent_chat.tools.base import Tool

logger = structlog.get_logger()

# NewsAPI supported country codes (subset of common ones)
_COUNTRY_ALIASES: dict[str, str] = {
    "中国": "cn", "china": "cn",
    "美国": "us", "usa": "us", "us": "us",
    "日本": "jp", "japan": "jp",
    "英国": "gb", "uk": "gb",
    "法国": "fr", "france": "fr",
    "德国": "de", "germany": "de",
    "韩国": "kr", "korea": "kr",
    "新加坡": "sg", "singapore": "sg",
    "澳大利亚": "au", "australia": "au",
    "加拿大": "ca", "canada": "ca",
    "印度": "in", "india": "in",
    "巴西": "br", "brazil": "br",
    "俄罗斯": "ru", "russia": "ru",
}

_CATEGORY_ALIASES: dict[str, str] = {
    "科技": "technology", "技术": "technology", "tech": "technology",
    "商业": "business", "财经": "business", "business": "business",
    "体育": "sports", "sport": "sports", "sports": "sports",
    "娱乐": "entertainment", "entertainment": "entertainment",
    "健康": "health", "health": "health",
    "科学": "science", "science": "science",
}


class NewsTool(Tool):
    name = "news"
    description = "查询今日热点新闻头条。可以按国家和类别筛选。"
    parameters = {
        "type": "object",
        "properties": {
            "country": {
                "type": "string",
                "description": "国家名称或代码，例如 us, jp, gb, 美国, 日本。默认 us（NewsAPI 对中国 cn 覆盖有限，建议用 us）",
            },
            "category": {
                "type": "string",
                "description": "新闻类别：technology/business/sports/entertainment/health/science/general。可用中文如 科技、商业、体育。默认 general",
            },
            "count": {
                "type": "integer",
                "description": "返回新闻条数，1-10，默认 5",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        api_key = settings.newsapi_key
        if not api_key:
            return {"error": "NewsAPI key not configured"}

        country_input = arguments.get("country", "us").strip().lower()
        category_input = arguments.get("category", "general").strip().lower()
        count = min(max(int(arguments.get("count", 5)), 1), 10)

        country = _COUNTRY_ALIASES.get(country_input, country_input)
        category = _CATEGORY_ALIASES.get(category_input, category_input)

        try:
            return await self._fetch_news(api_key, country, category, count)
        except httpx.HTTPError as e:
            logger.error("news_api_error", error=str(e))
            return {"error": f"无法连接新闻服务（{type(e).__name__}），请检查网络或代理设置"}

    async def _fetch_news(
        self, api_key: str, country: str, category: str, count: int
    ) -> dict[str, Any]:
        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.load_default_certs()
        async with httpx.AsyncClient(timeout=10.0, proxy=proxy, verify=ssl_ctx) as client:
            resp = await client.get(
                "https://newsapi.org/v2/top-headlines",
                params={
                    "country": country,
                    "category": category,
                    "pageSize": count,
                    "apiKey": api_key,
                },
            )
            data = resp.json()

        if data.get("status") != "ok":
            return {"error": data.get("message", "Unknown NewsAPI error")}

        raw_articles = data.get("articles", [])[:count]
        if not raw_articles:
            return {
                "country": country,
                "category": category,
                "total_results": 0,
                "articles": [],
                "note": f"No headlines found for country={country}, category={category}. Try country=us or a different category.",
            }

        articles = []
        for article in raw_articles:
            articles.append({
                "title": article.get("title", ""),
                "source": article.get("source", {}).get("name", ""),
                "description": article.get("description", ""),
                "url": article.get("url", ""),
                "published_at": article.get("publishedAt", ""),
            })

        return {
            "country": country,
            "category": category,
            "total_results": data.get("totalResults", 0),
            "articles": articles,
        }

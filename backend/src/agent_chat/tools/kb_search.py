"""Knowledge base search tool — semantic search across user's PDF and web content."""

from __future__ import annotations

from typing import Any

from agent_chat.services.kb_service import search_kb
from agent_chat.tools.base import Tool


class KBSearchTool(Tool):
    name = "kb_search"
    description = "搜索用户的个人知识库（PDF文档、网页等）。当用户问到已上传文档的内容、之前保存的信息时使用。"
    risk_level = "read"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词或问题",
            },
            "source_type": {
                "type": "string",
                "description": "来源类型过滤: pdf, webpage",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果数量，1-10，默认5",
            },
        },
        "required": ["query"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        user_id = (context or {}).get("user_id")
        if not user_id:
            return {"error": "User context required", "code": "NO_USER_CONTEXT"}

        query = arguments["query"]
        limit = min(max(arguments.get("limit", 5), 1), 10)
        source_type = arguments.get("source_type")

        results = await search_kb(
            user_id=user_id,
            query=query,
            limit=limit,
            source_type=source_type,
        )

        return {
            "query": query,
            "results": [
                {
                    "source_title": r.get("source_title", ""),
                    "source_type": r.get("source_type", ""),
                    "content": r.get("content", "")[:500],
                    "relevance": round(r.get("score", 0), 3),
                    "page_number": (r.get("metadata") or {}).get("page_number"),
                    "url": (r.get("metadata") or {}).get("url"),
                }
                for r in results
            ],
        }

"""search_memory tool — searches user's historical conversation memories."""

from __future__ import annotations

from typing import Any

from agent_chat.db.repository import search_memories_vector
from agent_chat.services.embedding_service import embed_text
from agent_chat.tools.base import Tool


class SearchMemoryTool(Tool):
    name = "search_memory"
    description = "搜索用户的历史对话记忆。当用户提到「之前」「上次」「我说过」「你还记得吗」等需要回忆历史信息时使用。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词或问题",
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
        user_id = context.get("user_id") if context else None
        if not user_id:
            return {"error": "No user context available"}

        query = arguments.get("query", "").strip()
        if not query:
            return {"error": "Missing query parameter"}

        limit = min(max(int(arguments.get("limit", 5)), 1), 10)

        query_embedding = await embed_text(query)
        results = await search_memories_vector(user_id, query_embedding, limit)

        return {
            "query": query,
            "memories": [
                {
                    "content": r["content"],
                    "type": r["memory_type"],
                    "relevance": round(r.get("score", 0), 3),
                    "date": str(r.get("created_at", "")),
                }
                for r in results
            ],
        }

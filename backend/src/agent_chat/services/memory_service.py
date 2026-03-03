"""Memory service — ingestion and compression of user messages."""

from __future__ import annotations

import structlog

from agent_chat.config import Settings
from agent_chat.db.repository import (
    create_memory,
    get_uncompressed_memories,
    mark_memories_compressed,
)
from agent_chat.llm.factory import create_provider
from agent_chat.services.embedding_service import embed_text

logger = structlog.get_logger()

COMPRESS_PROMPT = (
    "你是一个记忆压缩助手。请将以下用户消息压缩成1-3句话的摘要，"
    "保留关键信息、话题和用户偏好。只输出摘要，不要其他内容。"
)


async def ingest_user_message(user_id: str, conversation_id: str, content: str) -> None:
    """Embed and store a user message as a memory record."""
    try:
        embedding = await embed_text(content)
        await create_memory(
            user_id=user_id,
            conversation_id=conversation_id,
            content=content,
            embedding=embedding,
            memory_type="message",
        )
        logger.debug("memory_ingested", conversation_id=conversation_id)
    except Exception as e:
        logger.warning("memory_ingest_failed", error=str(e))


async def compress_conversation(
    conversation_id: str, user_id: str, settings: Settings
) -> None:
    """Compress uncompressed message memories into a summary."""
    try:
        memories = await get_uncompressed_memories(conversation_id)
        if len(memories) < 3:
            logger.debug("compress_skipped", reason="too_few_memories", count=len(memories))
            return

        combined = "\n".join(m["content"] for m in memories)

        provider = create_provider(settings)
        response = await provider.chat([
            {"role": "system", "content": COMPRESS_PROMPT},
            {"role": "user", "content": combined},
        ])
        summary = response.content.strip()

        embedding = await embed_text(summary)
        await create_memory(
            user_id=user_id,
            conversation_id=conversation_id,
            content=summary,
            embedding=embedding,
            memory_type="summary",
        )
        await mark_memories_compressed(conversation_id)
        logger.info(
            "conversation_compressed",
            conversation_id=conversation_id,
            original_count=len(memories),
        )
    except Exception as e:
        logger.warning("compress_failed", conversation_id=conversation_id, error=str(e))

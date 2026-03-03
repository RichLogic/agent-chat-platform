"""Memory management endpoints (authenticated)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import Response

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.config import get_settings
from agent_chat.db.repository import get_user_conversation
from agent_chat.services.memory_service import compress_conversation

router = APIRouter()


@router.post("/api/conversations/{conversation_id}/compress", status_code=202)
async def compress_endpoint(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Trigger memory compression for a conversation (runs in background)."""
    conversation = await get_user_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    settings = get_settings()
    asyncio.create_task(compress_conversation(conversation_id, user_id, settings))
    return {"status": "accepted"}

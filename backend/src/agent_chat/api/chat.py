"""Core SSE streaming chat endpoint."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.config import get_settings
from agent_chat.schemas.api import ChatRequest
from agent_chat.services.chat_service import handle_chat_stream

router = APIRouter()


@router.post("/api/chat")
async def chat(
    body: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    settings = get_settings()

    async def event_generator():
        async for event in handle_chat_stream(
            conversation_id=body.conversation_id,
            user_content=body.content,
            user_id=user_id,
            settings=settings,
        ):
            yield {
                "event": event["type"],
                "data": json.dumps(event, ensure_ascii=False, default=str),
            }

    return EventSourceResponse(event_generator())

"""Conversation CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import Response

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.db.repository import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
)

router = APIRouter()


@router.get("/api/conversations")
async def list_conversations_endpoint(
    user_id: str = Depends(get_current_user_id),
) -> dict:
    conversations = await list_conversations(user_id)
    return {"items": conversations}


@router.post("/api/conversations")
async def create_conversation_endpoint(
    user_id: str = Depends(get_current_user_id),
) -> dict:
    conversation = await create_conversation(user_id)
    return conversation


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> Response:
    conversation = await get_conversation(conversation_id)
    if not conversation or conversation.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await delete_conversation(conversation_id, user_id)
    return Response(status_code=204)

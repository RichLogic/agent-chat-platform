"""Conversation CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import Response

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.db.repository import (
    cascade_delete_conversation,
    create_conversation,
    get_active_run_for_conversation,
    get_conversation_stats,
    get_user_conversation,
    get_user_stats,
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
    conversation = await get_user_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await cascade_delete_conversation(conversation_id, user_id)
    return Response(status_code=204)


@router.get("/api/conversations/{conversation_id}/stats")
async def get_conversation_stats_endpoint(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    conversation = await get_user_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return await get_conversation_stats(conversation_id)


@router.get("/api/conversations/{conversation_id}/active-run")
async def get_active_run_endpoint(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    conversation = await get_user_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    run = await get_active_run_for_conversation(conversation_id)
    return {"active_run": run}


@router.get("/api/stats")
async def get_stats_endpoint(
    user_id: str = Depends(get_current_user_id),
) -> dict:
    return await get_user_stats(user_id)

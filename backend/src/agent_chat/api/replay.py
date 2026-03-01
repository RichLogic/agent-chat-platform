"""Replay and message list endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.db.repository import get_conversation, get_run, list_messages
from agent_chat.config import get_settings
from agent_chat.storage.file_store import read_events

router = APIRouter()


@router.get("/api/runs/{run_id}/events")
async def replay_run_events(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Read JSONL file and stream as SSE events."""
    run = await get_run(run_id)
    if not run or run.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Run not found")

    settings = get_settings()

    async def event_generator():
        async for event in read_events(settings.data_dir, run_id):
            yield {
                "event": event["type"],
                "data": json.dumps(event, ensure_ascii=False, default=str),
            }

    return EventSourceResponse(event_generator())


@router.get("/api/conversations/{conversation_id}/messages")
async def list_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """List all messages in a conversation."""
    conversation = await get_conversation(conversation_id)
    if not conversation or conversation.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await list_messages(conversation_id)
    return {"items": messages}

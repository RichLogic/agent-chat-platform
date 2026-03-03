"""Replay and message list endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.db.repository import get_files_by_ids, get_run, get_user_conversation, list_messages
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
    conversation = await get_user_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await list_messages(conversation_id)

    # Resolve file_ids to file metadata for frontend display
    all_file_ids: set[str] = set()
    for msg in messages:
        fids = msg.get("file_ids")
        if fids:
            all_file_ids.update(fids)

    if all_file_ids:
        files = await get_files_by_ids(list(all_file_ids))
        files_map = {f["id"]: f for f in files}
        for msg in messages:
            fids = msg.get("file_ids")
            if fids:
                msg["files"] = [
                    {
                        "id": files_map[fid]["id"],
                        "original_filename": files_map[fid]["original_filename"],
                        "size_bytes": files_map[fid]["size_bytes"],
                        "page_count": files_map[fid].get("page_count"),
                    }
                    for fid in fids
                    if fid in files_map
                ]

    return {"items": messages}

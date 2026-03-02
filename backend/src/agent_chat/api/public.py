"""Public endpoints for shared conversations (no auth required)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agent_chat.config import get_settings
from agent_chat.db.repository import (
    get_conversation,
    get_files_by_ids,
    get_share_by_token,
    list_messages,
    list_runs_by_conversation,
)

router = APIRouter()


@router.get("/api/shared/{share_token}")
async def get_shared_conversation(share_token: str) -> dict:
    share = await get_share_by_token(share_token)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    conversation = await get_conversation(share["conversation_id"])
    if not conversation or conversation.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await list_messages(share["conversation_id"])

    # Resolve file_ids to file metadata
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

    return {
        "conversation": {
            "title": conversation.get("title", ""),
            "created_at": str(conversation.get("created_at", "")),
        },
        "messages": messages,
    }


@router.get("/api/shared/{share_token}/events")
async def get_shared_events(share_token: str) -> dict:
    share = await get_share_by_token(share_token)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    conversation = await get_conversation(share["conversation_id"])
    if not conversation or conversation.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Conversation not found")

    runs = await list_runs_by_conversation(share["conversation_id"])
    settings = get_settings()

    all_events: list[dict] = []
    for run in runs:
        run_id = run["id"]
        events_file = Path(settings.data_dir) / "runs" / run_id / "events.jsonl"
        if not events_file.exists():
            continue
        with open(events_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    event = json.loads(line)
                    event["run_id"] = run_id
                    all_events.append(event)

    return {"events": all_events}

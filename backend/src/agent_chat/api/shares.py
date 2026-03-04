"""Share management endpoints (authenticated)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import Response

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.config import get_settings
from agent_chat.db.repository import (
    create_share,
    delete_share,
    get_share_by_conversation,
    get_user_conversation,
)

router = APIRouter()


def _build_share_url(token: str) -> str:
    base = get_settings().frontend_url.rstrip("/")
    return f"{base}/s/{token}"


@router.post("/api/conversations/{conversation_id}/share")
async def create_share_endpoint(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    conversation = await get_user_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    existing = await get_share_by_conversation(conversation_id)
    if existing:
        return {
            "share_token": existing["share_token"],
            "share_url": _build_share_url(existing["share_token"]),
        }

    token = secrets.token_urlsafe(9)
    await create_share(token, conversation_id, user_id)
    return {
        "share_token": token,
        "share_url": _build_share_url(token),
    }


@router.delete("/api/conversations/{conversation_id}/share")
async def delete_share_endpoint(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> Response:
    conversation = await get_user_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await delete_share(conversation_id, user_id)
    return Response(status_code=204)


@router.get("/api/conversations/{conversation_id}/share")
async def get_share_status_endpoint(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    conversation = await get_user_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    existing = await get_share_by_conversation(conversation_id)
    if existing:
        return {
            "shared": True,
            "share_token": existing["share_token"],
            "share_url": _build_share_url(existing["share_token"]),
        }
    return {"shared": False}

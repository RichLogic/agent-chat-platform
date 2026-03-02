"""Aggregate all API routes."""

from __future__ import annotations

from fastapi import APIRouter

from agent_chat.api import auth, chat, conversations, files, public, replay, shares

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(conversations.router)
api_router.include_router(chat.router)
api_router.include_router(replay.router)
api_router.include_router(files.router)
api_router.include_router(shares.router)
api_router.include_router(public.router)

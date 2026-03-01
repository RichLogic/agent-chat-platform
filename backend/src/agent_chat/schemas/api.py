"""Pydantic models for REST API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    conversation_id: str
    content: str


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    run_id: str | None = None
    token_usage: dict | None = None
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]


class UserResponse(BaseModel):
    id: str
    github_login: str
    display_name: str
    avatar_url: str
    email: str

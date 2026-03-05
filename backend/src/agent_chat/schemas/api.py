"""Pydantic models for REST API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    conversation_id: str
    content: str
    file_ids: list[str] | None = None
    agent_mode: bool = False


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]


class FileInfoResponse(BaseModel):
    id: str
    original_filename: str
    size_bytes: int
    page_count: int | None = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    run_id: str | None = None
    token_usage: dict | None = None
    file_ids: list[str] | None = None
    files: list[FileInfoResponse] | None = None
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]


class UserResponse(BaseModel):
    id: str
    github_login: str
    display_name: str
    avatar_url: str
    email: str

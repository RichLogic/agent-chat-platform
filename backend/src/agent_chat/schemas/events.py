"""SSE event type definitions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RunStartData(BaseModel):
    run_id: str
    provider: str
    model: str


class TextDeltaData(BaseModel):
    content: str


class RunFinishData(BaseModel):
    finish_reason: str
    token_usage: dict | None = None


class ConversationTitleData(BaseModel):
    title: str


class ErrorData(BaseModel):
    message: str


class SSEEvent(BaseModel):
    type: str
    ts: datetime
    data: dict

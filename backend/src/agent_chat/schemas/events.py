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


class ToolCallData(BaseModel):
    tool_name: str
    arguments: dict
    risk_level: str = "read"
    step_index: int = 0


class ToolResultData(BaseModel):
    tool_name: str
    result: dict
    error_code: str | None = None
    step_index: int = 0


class ProviderFallbackData(BaseModel):
    from_provider: str
    to_provider: str
    reason: str


class ErrorData(BaseModel):
    message: str


class SSEEvent(BaseModel):
    type: str
    ts: datetime
    data: dict

"""Pydantic schema validation tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent_chat.schemas.api import ChatRequest, ConversationResponse, MessageResponse
from agent_chat.schemas.events import (
    ConversationTitleData,
    RunFinishData,
    RunStartData,
    SSEEvent,
    TextDeltaData,
)


def test_chat_request():
    req = ChatRequest(conversation_id="conv-1", content="Hello")
    assert req.conversation_id == "conv-1"
    assert req.content == "Hello"

    with pytest.raises(ValidationError):
        ChatRequest(conversation_id="conv-1")  # missing content

    with pytest.raises(ValidationError):
        ChatRequest(content="Hello")  # missing conversation_id


def test_conversation_response():
    now = datetime.now(timezone.utc)
    resp = ConversationResponse(id="c1", title="Test", created_at=now, updated_at=now)
    data = resp.model_dump()
    assert data["id"] == "c1"
    assert data["title"] == "Test"

    # Round-trip
    restored = ConversationResponse.model_validate(data)
    assert restored.id == resp.id
    assert restored.title == resp.title


def test_sse_event_models():
    start = RunStartData(run_id="r1", provider="poe", model="gpt")
    assert start.run_id == "r1"

    delta = TextDeltaData(content="hello")
    assert delta.content == "hello"

    finish = RunFinishData(finish_reason="stop", token_usage={"total_tokens": 10})
    assert finish.finish_reason == "stop"
    assert finish.token_usage["total_tokens"] == 10

    title = ConversationTitleData(title="Chat Title")
    assert title.title == "Chat Title"

    now = datetime.now(timezone.utc)
    event = SSEEvent(type="run.start", ts=now, data={"run_id": "r1"})
    assert event.type == "run.start"

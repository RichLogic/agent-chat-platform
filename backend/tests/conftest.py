"""Global test fixtures."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import patch

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.config import Settings, set_settings
from agent_chat.llm.provider import ChatResponse, StreamChunk

TEST_USER_ID = "000000000000000000000001"


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        _env_file=None,
        mongo_uri="mongodb://localhost:27017",
        mongo_db="test_db",
        data_dir=str(tmp_path / "data"),
        jwt_secret="test-secret-key-for-testing",
        jwt_expiry_minutes=60,
        github_client_id="test-client-id",
        github_client_secret="test-client-secret",
        frontend_url="http://localhost:3000",
        llm_provider="poe",
        poe_api_key="test-key",
        poe_model="test-model",
        poe_base_url="https://test.example.com/v1",
        log_level="WARNING",
    )


@pytest.fixture
def mock_db(monkeypatch):
    client = AsyncMongoMockClient()
    db = client["test_db"]
    monkeypatch.setattr("agent_chat.db.mongo._db", db)
    return db


class MockLLMProvider:
    def __init__(self):
        self.provider_name = "mock"
        self.model = "mock-model"

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(content="Hello! ")
        yield StreamChunk(content="How can I help?")
        yield StreamChunk(
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        )

    async def chat(self, messages: list[dict]) -> ChatResponse:
        return ChatResponse(
            content="Test Title",
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        )


@pytest.fixture
def test_app(test_settings, mock_db):
    set_settings(test_settings)

    from fastapi import FastAPI

    from agent_chat.api.router import api_router

    app = FastAPI()
    app.include_router(api_router)

    async def override_get_current_user_id():
        return TEST_USER_ID

    app.dependency_overrides[get_current_user_id] = override_get_current_user_id

    mock_provider = MockLLMProvider()
    with (
        patch(
            "agent_chat.services.chat_service.create_provider",
            return_value=mock_provider,
        ),
        patch(
            "agent_chat.services.title_service.create_provider",
            return_value=mock_provider,
        ),
    ):
        yield app


@pytest.fixture
async def client(test_app):
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def collect_sse_events(response: httpx.Response) -> list[dict]:
    """Collect all SSE events from an httpx streaming response."""
    events = []
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    if buffer.strip().startswith("data: "):
        events.append(json.loads(buffer.strip()[6:]))
    return events

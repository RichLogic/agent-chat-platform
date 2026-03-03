"""Tests for multi-step tool loop and FallbackProvider."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from agent_chat.llm.factory import FallbackProvider
from agent_chat.llm.provider import ChatResponse, StreamChunk


# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------

class MockProvider:
    """LLMProvider mock that yields configurable responses."""

    def __init__(self, responses: list[str], provider_name: str = "mock", model: str = "mock-model"):
        self.provider_name = provider_name
        self.model = model
        self._responses = responses
        self._call_count = 0

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[StreamChunk]:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        for char in self._responses[idx]:
            yield StreamChunk(content=char)
        yield StreamChunk(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    async def chat(self, messages: list[dict]) -> ChatResponse:
        return ChatResponse(content="title", usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8})


class FailingProvider:
    """Provider that raises on stream_chat."""

    def __init__(self, provider_name: str = "failing"):
        self.provider_name = provider_name
        self.model = "failing-model"

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[StreamChunk]:
        raise ConnectionError("Provider unavailable")
        yield  # make it a generator  # pragma: no cover

    async def chat(self, messages: list[dict]) -> ChatResponse:
        raise ConnectionError("Provider unavailable")


# ---------------------------------------------------------------------------
# Tests — FallbackProvider
# ---------------------------------------------------------------------------

class TestFallbackProvider:
    @pytest.mark.asyncio
    async def test_primary_works(self) -> None:
        primary = MockProvider(["Hello!"], provider_name="primary")
        fallback = MockProvider(["Backup!"], provider_name="fallback")
        fp = FallbackProvider(primary, fallback)

        chunks = []
        async for chunk in fp.stream_chat([{"role": "user", "content": "hi"}]):
            if chunk.content:
                chunks.append(chunk.content)

        assert "".join(chunks) == "Hello!"
        assert fp.used_fallback is False
        assert fp.provider_name == "primary"

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self) -> None:
        primary = FailingProvider(provider_name="primary")
        fallback = MockProvider(["Backup!"], provider_name="fallback")
        fp = FallbackProvider(primary, fallback)

        chunks = []
        async for chunk in fp.stream_chat([{"role": "user", "content": "hi"}]):
            if chunk.content:
                chunks.append(chunk.content)

        assert "".join(chunks) == "Backup!"
        assert fp.used_fallback is True
        assert fp.provider_name == "fallback"

    @pytest.mark.asyncio
    async def test_no_fallback_raises(self) -> None:
        primary = FailingProvider(provider_name="primary")
        fp = FallbackProvider(primary, fallback=None)

        with pytest.raises(ConnectionError):
            async for _ in fp.stream_chat([{"role": "user", "content": "hi"}]):
                pass

    @pytest.mark.asyncio
    async def test_chat_fallback(self) -> None:
        primary = FailingProvider(provider_name="primary")
        fallback = MockProvider(["unused"], provider_name="fallback")
        fp = FallbackProvider(primary, fallback)

        result = await fp.chat([{"role": "user", "content": "hi"}])
        assert result.content == "title"
        assert fp.used_fallback is True

    @pytest.mark.asyncio
    async def test_chat_no_fallback_raises(self) -> None:
        primary = FailingProvider(provider_name="primary")
        fp = FallbackProvider(primary, fallback=None)

        with pytest.raises(ConnectionError):
            await fp.chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# Tests — Multi-step tool loop (_try_parse_tool_call + _merge_usage)
# ---------------------------------------------------------------------------

class TestToolCallParsing:
    def test_valid_tool_call(self) -> None:
        from agent_chat.services.chat_service import _try_parse_tool_call
        text = json.dumps({"tool": "weather", "arguments": {"city": "Beijing"}})
        result = _try_parse_tool_call(text)
        assert result is not None
        assert result["tool"] == "weather"
        assert result["arguments"]["city"] == "Beijing"

    def test_tool_call_with_whitespace(self) -> None:
        from agent_chat.services.chat_service import _try_parse_tool_call
        text = '  \n  {"tool": "search", "arguments": {"query": "test"}}  \n'
        result = _try_parse_tool_call(text)
        assert result is not None
        assert result["tool"] == "search"

    def test_non_json_text(self) -> None:
        from agent_chat.services.chat_service import _try_parse_tool_call
        assert _try_parse_tool_call("Hello, how are you?") is None

    def test_json_without_tool_key(self) -> None:
        from agent_chat.services.chat_service import _try_parse_tool_call
        assert _try_parse_tool_call('{"key": "value"}') is None

    def test_invalid_json(self) -> None:
        from agent_chat.services.chat_service import _try_parse_tool_call
        assert _try_parse_tool_call('{invalid json}') is None

    def test_non_brace_start(self) -> None:
        from agent_chat.services.chat_service import _try_parse_tool_call
        assert _try_parse_tool_call('Not a json string') is None


class TestMergeUsage:
    def test_both_none(self) -> None:
        from agent_chat.services.chat_service import _merge_usage
        assert _merge_usage(None, None) is None

    def test_a_none(self) -> None:
        from agent_chat.services.chat_service import _merge_usage
        b = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        assert _merge_usage(None, b) == b

    def test_b_none(self) -> None:
        from agent_chat.services.chat_service import _merge_usage
        a = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        assert _merge_usage(a, None) == a

    def test_merge(self) -> None:
        from agent_chat.services.chat_service import _merge_usage
        a = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        b = {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
        result = _merge_usage(a, b)
        assert result == {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45}

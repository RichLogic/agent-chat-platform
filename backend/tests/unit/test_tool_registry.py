"""Tests for ToolRegistry — schema validation, timeout, retry."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent_chat.tools.base import Tool
from agent_chat.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class EchoTool(Tool):
    """Simple tool that echoes its arguments."""
    name = "echo"
    description = "Echoes arguments back."
    risk_level = "read"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "message to echo"},
        },
        "required": ["message"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"echoed": arguments["message"]}


class SlowTool(Tool):
    """Tool that sleeps forever — used to test timeout."""
    name = "slow"
    description = "Takes forever."
    risk_level = "read"
    timeout_seconds = 0.1  # very short for testing
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        await asyncio.sleep(999)
        return {"done": True}  # pragma: no cover


class FlakeyTool(Tool):
    """Tool that fails N times then succeeds — used to test retry."""
    name = "flakey"
    description = "Fails then succeeds."
    risk_level = "read"
    timeout_seconds = 5.0
    max_retries = 2  # up to 3 total attempts
    parameters = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, fail_count: int = 2) -> None:
        self._fail_count = fail_count
        self._attempt = 0

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self._attempt += 1
        if self._attempt <= self._fail_count:
            raise RuntimeError(f"Boom (attempt {self._attempt})")
        return {"ok": True, "attempts": self._attempt}


# ---------------------------------------------------------------------------
# Tests — Schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def setup_method(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register(EchoTool())

    @pytest.mark.asyncio
    async def test_valid_params(self) -> None:
        result = await self.registry.execute("echo", {"message": "hello"})
        assert result["echoed"] == "hello"
        assert result["_meta"]["attempts"] == 1

    @pytest.mark.asyncio
    async def test_missing_required_param(self) -> None:
        result = await self.registry.execute("echo", {})
        assert result["code"] == "INVALID_PARAMS"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_wrong_type_param(self) -> None:
        result = await self.registry.execute("echo", {"message": 123})
        assert result["code"] == "INVALID_PARAMS"

    @pytest.mark.asyncio
    async def test_unknown_tool(self) -> None:
        result = await self.registry.execute("nonexistent", {})
        assert result["code"] == "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# Tests — Timeout
# ---------------------------------------------------------------------------

class TestTimeout:
    def setup_method(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register(SlowTool())

    @pytest.mark.asyncio
    async def test_timeout_returns_code(self) -> None:
        result = await self.registry.execute("slow", {})
        assert result["code"] == "TIMEOUT"
        assert "timed out" in result["error"]


# ---------------------------------------------------------------------------
# Tests — Retry
# ---------------------------------------------------------------------------

class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self) -> None:
        registry = ToolRegistry()
        tool = FlakeyTool(fail_count=2)
        registry.register(tool)

        with patch("agent_chat.tools.registry.asyncio.sleep", new_callable=AsyncMock):
            result = await registry.execute("flakey", {})

        assert result["ok"] is True
        assert result["attempts"] == 3
        assert result["_meta"]["attempts"] == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self) -> None:
        registry = ToolRegistry()
        tool = FlakeyTool(fail_count=99)  # always fails
        registry.register(tool)

        with patch("agent_chat.tools.registry.asyncio.sleep", new_callable=AsyncMock):
            result = await registry.execute("flakey", {})

        assert result["code"] == "EXECUTION_ERROR"
        assert "Boom" in result["error"]


# ---------------------------------------------------------------------------
# Tests — generate_schema includes risk_level
# ---------------------------------------------------------------------------

class TestGenerateSchema:
    def test_schema_contains_risk_level(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        import json
        schema = json.loads(registry.generate_schema())
        assert len(schema) == 1
        assert schema[0]["risk_level"] == "read"
        assert schema[0]["name"] == "echo"

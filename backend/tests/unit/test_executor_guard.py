from __future__ import annotations

import pytest

from agent_chat.tools.registry import (
    ExecutionGuard,
    ExecutionRequest,
)


@pytest.mark.asyncio
async def test_guard_blocks_denylist() -> None:
    guard = ExecutionGuard(denylist={"rm"})
    result = await guard.validate(
        ExecutionRequest(command="rm -rf /tmp/x", tool_name="shell", risk_level="destructive")
    )
    assert result.ok is False
    assert result.code == "DENYLIST_BLOCKED"


@pytest.mark.asyncio
async def test_guard_blocks_not_allowlisted() -> None:
    guard = ExecutionGuard(allowlist={"echo"})
    result = await guard.validate(
        ExecutionRequest(command="cat /etc/hosts", tool_name="shell", risk_level="read")
    )
    assert result.ok is False
    assert result.code == "NOT_IN_ALLOWLIST"


@pytest.mark.asyncio
async def test_guard_allows_safe_command() -> None:
    guard = ExecutionGuard(allowlist={"echo"}, denylist={"rm"})
    result = await guard.validate(
        ExecutionRequest(command="echo hello", tool_name="shell", risk_level="read")
    )
    assert result.ok is True
    assert result.code == "ALLOWED"

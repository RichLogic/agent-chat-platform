from __future__ import annotations

import pytest

from agent_chat.security.policy import Decision, PolicyEngine
from agent_chat.tools.command import CommandTool


def test_command_tool_risk_levels() -> None:
    tool = CommandTool()
    assert tool.get_risk_level({"command": "cat /tmp/x"}) == "read"
    assert tool.get_risk_level({"command": "touch /tmp/x"}) == "write"
    assert tool.get_risk_level({"command": "rm -rf /tmp/x"}) == "destructive"
    assert tool.get_risk_level({"command": "sudo ls"}) == "admin"


def test_command_policy_denies_rm() -> None:
    engine = PolicyEngine()
    result = engine.evaluate(CommandTool(), {"command": "rm -rf /tmp/x"})
    assert result.decision == Decision.DENY


@pytest.mark.asyncio
async def test_command_tool_exec_error() -> None:
    tool = CommandTool()
    with pytest.raises(RuntimeError):
        await tool.execute({"command": "nonexistent_cmd --demo"})

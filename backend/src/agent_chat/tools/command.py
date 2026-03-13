"""Command tool used for reliability and approval/policy demonstrations."""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from agent_chat.tools.base import Tool

_WRITE_COMMANDS = {"touch", "mkdir", "tee", "cp", "mv", "truncate"}
_DESTRUCTIVE_COMMANDS = {"rm", "dd", "mkfs"}
_ADMIN_COMMANDS = {"sudo"}


class CommandTool(Tool):
    name = "command"
    description = (
        "执行 shell 命令的演示工具。适用于需要展示 approval、policy denied、timeout、"
        "execution error 等可靠性路径的场景。"
    )
    risk_level = "write"
    timeout_seconds = 5.0
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令",
            },
        },
        "required": ["command"],
    }

    def get_risk_level(self, arguments: dict[str, Any] | None = None) -> str:
        command = str((arguments or {}).get("command", "")).strip()
        if not command:
            return "read"

        try:
            base = shlex.split(command)[0]
        except ValueError:
            base = command.split()[0] if command.split() else ""

        if base in _ADMIN_COMMANDS:
            return "admin"
        if base in _DESTRUCTIVE_COMMANDS:
            return "destructive"
        if base in _WRITE_COMMANDS:
            return "write"
        return "read"

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        command = arguments["command"].strip()
        parts = shlex.split(command)
        base = parts[0] if parts else ""

        if base == "sleep":
            duration = 10.0
            if len(parts) > 1:
                try:
                    duration = float(parts[1])
                except ValueError:
                    duration = 10.0
            await asyncio.sleep(duration)
            return {"ok": True, "command": command, "exit_code": 0}

        if base in {"false", "nonexistent_cmd", "simulate-error"}:
            raise RuntimeError(f"simulated command failure: {command}")

        return {
            "ok": True,
            "command": command,
            "stdout": f"Simulated execution: {command}",
            "exit_code": 0,
        }

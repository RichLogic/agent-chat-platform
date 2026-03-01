"""Tool registry — manages available tools, generates schemas, executes tools."""

from __future__ import annotations

import json
from typing import Any

from agent_chat.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def generate_schema(self) -> str:
        """Generate a JSON string describing all registered tools for prompt injection."""
        tools = []
        for tool in self._tools.values():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            })
        return json.dumps(tools, ensure_ascii=False, indent=2)

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}
        return await tool.execute(arguments)


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Get or create the global tool registry with all tools registered."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_all_tools(_registry)
    return _registry


def _register_all_tools(registry: ToolRegistry) -> None:
    from agent_chat.tools.weather import WeatherTool
    from agent_chat.tools.news import NewsTool
    from agent_chat.tools.search import SearchTool
    registry.register(WeatherTool())
    registry.register(NewsTool())
    registry.register(SearchTool())

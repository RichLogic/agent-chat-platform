"""Tool registry — manages available tools, generates schemas, executes tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import jsonschema
import structlog

from agent_chat.tools.base import Tool

logger = structlog.get_logger()


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
                "risk_level": tool.risk_level,
            })
        return json.dumps(tools, ensure_ascii=False, indent=2)

    async def execute(
        self, name: str, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}", "code": "UNKNOWN_TOOL"}

        # --- Schema validation ---
        try:
            jsonschema.validate(instance=arguments, schema=tool.parameters)
        except jsonschema.ValidationError as exc:
            return {"error": exc.message, "code": "INVALID_PARAMS"}

        # --- Execute with timeout + retry ---
        attempts = 1 + tool.max_retries
        last_error: str = ""
        for attempt in range(1, attempts + 1):
            try:
                result = await asyncio.wait_for(
                    tool.execute(arguments, context),
                    timeout=tool.timeout_seconds,
                )
                return result
            except asyncio.TimeoutError:
                last_error = (
                    f"Tool '{name}' timed out after {tool.timeout_seconds}s"
                )
                logger.warning(
                    "tool_timeout",
                    tool=name,
                    attempt=attempt,
                    timeout=tool.timeout_seconds,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "tool_execution_error",
                    tool=name,
                    attempt=attempt,
                    error=last_error,
                )

            if attempt < attempts:
                await asyncio.sleep(min(2 ** (attempt - 1), 4))

        # All attempts exhausted
        code = "TIMEOUT" if "timed out" in last_error else "EXECUTION_ERROR"
        return {"error": last_error, "code": code}


_registry: ToolRegistry | None = None


async def get_registry() -> ToolRegistry:
    """Get or create the global tool registry with all tools registered."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        await _register_all_tools(_registry)
    return _registry


async def _register_all_tools(registry: ToolRegistry) -> None:
    from agent_chat.tools.weather import WeatherTool
    from agent_chat.tools.news import NewsTool
    from agent_chat.tools.search import SearchTool
    from agent_chat.tools.read_pdf import ReadPdfTool
    from agent_chat.tools.search_memory import SearchMemoryTool
    from agent_chat.tools.kb_search import KBSearchTool
    from agent_chat.tools.ingest_webpage import IngestWebpageTool
    registry.register(WeatherTool())
    registry.register(NewsTool())
    registry.register(SearchTool())
    registry.register(ReadPdfTool())
    registry.register(SearchMemoryTool())
    registry.register(KBSearchTool())
    registry.register(IngestWebpageTool())

    # MCP tool discovery (optional, non-blocking)
    try:
        from agent_chat.config import get_settings
        settings = get_settings()
        if settings.mcp_notes_url:
            from agent_chat.tools.mcp_adapter import discover_and_register_mcp_tools
            count = await discover_and_register_mcp_tools(registry, settings.mcp_notes_url)
            logger.info("mcp_tools_discovered", count=count, url=settings.mcp_notes_url)
    except Exception as e:
        logger.debug("mcp_tools_skipped", reason=str(e))

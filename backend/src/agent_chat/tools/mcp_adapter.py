"""MCP tool adapter — wraps remote MCP tools as local Tool instances."""

from __future__ import annotations

from typing import Any

import structlog

from agent_chat.tools.base import Tool

logger = structlog.get_logger()


class McpTool(Tool):
    """A Tool backed by a remote MCP server."""

    risk_level = "write"
    timeout_seconds = 15.0

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        mcp_url: str,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self._mcp_url = mcp_url

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        try:
            async with streamablehttp_client(self._mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(self.name, arguments)
                    # Extract text content from result
                    if result.content:
                        text = result.content[0].text
                        return {"content": text}
                    return {"content": ""}
        except Exception as e:
            logger.error("mcp_tool_error", tool=self.name, error=str(e))
            return {"error": str(e), "code": "MCP_ERROR"}


async def discover_and_register_mcp_tools(
    registry: Any,
    mcp_url: str,
) -> int:
    """Connect to an MCP server, discover its tools, and register them.

    Returns the number of tools registered.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()

            count = 0
            for t in tools_result.tools:
                tool = McpTool(
                    name=t.name,
                    description=t.description or "",
                    parameters=t.inputSchema,
                    mcp_url=mcp_url,
                )
                registry.register(tool)
                count += 1
                logger.info("mcp_tool_registered", name=t.name)

            return count

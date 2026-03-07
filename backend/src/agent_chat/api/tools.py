"""Tool management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.tools.registry import get_registry, refresh_mcp_tools

router = APIRouter()


@router.post("/api/tools/refresh-mcp")
async def refresh_mcp(user_id: str = Depends(get_current_user_id)) -> dict:
    """Re-discover and register MCP tools from configured MCP server."""
    try:
        count = await refresh_mcp_tools()
        return {"status": "ok", "tools_registered": count}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MCP refresh failed: {e}")


@router.get("/api/tools")
async def list_tools(user_id: str = Depends(get_current_user_id)) -> dict:
    """List all registered tools."""
    registry = await get_registry()
    tools = [
        {"name": t.name, "description": t.description, "risk_level": t.risk_level}
        for t in registry._tools.values()
    ]
    return {"tools": tools}

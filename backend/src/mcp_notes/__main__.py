"""Entry point for ``python -m mcp_notes``."""

from mcp_notes.server import mcp

mcp.run(transport="streamable-http", host="0.0.0.0", port=8302)

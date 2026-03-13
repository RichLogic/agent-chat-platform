"""MCP Notes Server."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

NOTES_ROOT = Path(os.environ.get("NOTES_ROOT", "data/notes"))

mcp = FastMCP("notes", stateless_http=True)


def _sanitize_filename(name: str) -> str:
    """Replace unsafe path characters and clamp the filename length."""
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    safe = safe.strip(". ")
    return safe[:100] or "untitled"


@mcp.tool()
def create_markdown_note(
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> str:
    """Create a markdown note under the inbox folder."""
    safe_name = _sanitize_filename(title)
    path = NOTES_ROOT / "inbox" / f"{safe_name}.md"

    if not path.resolve().is_relative_to(NOTES_ROOT.resolve()):
        raise ValueError("Invalid path - path traversal detected")

    path.parent.mkdir(parents=True, exist_ok=True)

    tag_str = ", ".join(tags) if tags else ""
    frontmatter = (
        f"---\n"
        f"title: {title}\n"
        f"tags: [{tag_str}]\n"
        f"date: {datetime.now().isoformat()}\n"
        f"---\n\n"
    )
    path.write_text(frontmatter + content, encoding="utf-8")
    return f"Created: {path.relative_to(NOTES_ROOT)}"


@mcp.tool()
def list_notes(folder: str = "inbox") -> str:
    """List markdown notes in a folder."""
    target = NOTES_ROOT / folder

    if not target.resolve().is_relative_to(NOTES_ROOT.resolve()):
        raise ValueError("Invalid path - path traversal detected")

    if not target.exists():
        return "Folder not found"

    files = sorted(target.glob("*.md"))
    if not files:
        return "No notes found"

    return "\n".join(f.stem for f in files)


@mcp.tool()
def read_note(folder: str = "inbox", name: str = "") -> str:
    """Read the contents of a markdown note."""
    if not name:
        return "Error: name is required"

    safe_name = _sanitize_filename(name)
    path = NOTES_ROOT / folder / f"{safe_name}.md"

    if not path.resolve().is_relative_to(NOTES_ROOT.resolve()):
        raise ValueError("Invalid path - path traversal detected")

    if not path.exists():
        return f"Note not found: {safe_name}"

    return path.read_text(encoding="utf-8")

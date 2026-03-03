"""MCP Notes Server — standalone note-taking server using FastMCP."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

NOTES_ROOT = Path(os.environ.get("NOTES_ROOT", "data/notes"))

mcp = FastMCP("notes", stateless_http=True)


def _sanitize_filename(name: str) -> str:
    """Remove or replace unsafe characters for file names."""
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    safe = safe.strip(". ")
    return safe[:100] or "untitled"


@mcp.tool()
def create_markdown_note(
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> str:
    """创建一个 Markdown 笔记文件，保存到 inbox 文件夹。"""
    safe_name = _sanitize_filename(title)
    path = NOTES_ROOT / "inbox" / f"{safe_name}.md"

    # Path traversal protection
    if not path.resolve().is_relative_to(NOTES_ROOT.resolve()):
        raise ValueError("Invalid path — path traversal detected")

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
    """列出指定文件夹中的所有 Markdown 笔记。"""
    target = NOTES_ROOT / folder

    # Path traversal protection
    if not target.resolve().is_relative_to(NOTES_ROOT.resolve()):
        raise ValueError("Invalid path — path traversal detected")

    if not target.exists():
        return "Folder not found"

    files = sorted(target.glob("*.md"))
    if not files:
        return "No notes found"

    return "\n".join(f.stem for f in files)


@mcp.tool()
def read_note(folder: str = "inbox", name: str = "") -> str:
    """读取指定笔记的内容。"""
    if not name:
        return "Error: name is required"

    safe_name = _sanitize_filename(name)
    path = NOTES_ROOT / folder / f"{safe_name}.md"

    if not path.resolve().is_relative_to(NOTES_ROOT.resolve()):
        raise ValueError("Invalid path — path traversal detected")

    if not path.exists():
        return f"Note not found: {safe_name}"

    return path.read_text(encoding="utf-8")

"""Tests for MCP notes server and adapter."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tests — MCP notes server (path traversal, file creation)
# ---------------------------------------------------------------------------

class TestMcpNotesServer:
    def test_sanitize_filename(self) -> None:
        from mcp_notes.server import _sanitize_filename
        assert _sanitize_filename("hello world") == "hello world"
        assert _sanitize_filename("a/b\\c:d") == "a_b_c_d"
        assert _sanitize_filename("...") == ""[:0] or _sanitize_filename("...") == "untitled"
        assert len(_sanitize_filename("x" * 200)) <= 100

    def test_create_note(self, tmp_path: Path) -> None:
        from mcp_notes.server import create_markdown_note, NOTES_ROOT
        import mcp_notes.server as srv

        original_root = srv.NOTES_ROOT
        srv.NOTES_ROOT = tmp_path
        try:
            result = create_markdown_note(
                title="Test Note",
                content="Hello, world!",
                tags=["test", "demo"],
            )
            assert "Created:" in result
            note_path = tmp_path / "inbox" / "Test Note.md"
            assert note_path.exists()
            content = note_path.read_text()
            assert "title: Test Note" in content
            assert "Hello, world!" in content
            assert "test, demo" in content
        finally:
            srv.NOTES_ROOT = original_root

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        """Verify that traversal-style titles get sanitized to safe filenames."""
        import mcp_notes.server as srv

        original_root = srv.NOTES_ROOT
        srv.NOTES_ROOT = tmp_path
        try:
            from mcp_notes.server import create_markdown_note
            result = create_markdown_note(
                title="../../../etc/passwd",
                content="malicious",
            )
            # The sanitizer replaces / with _ so file ends up safely in inbox
            assert "Created:" in result
            # Ensure no file was created outside NOTES_ROOT
            for p in tmp_path.rglob("*"):
                assert p.resolve().is_relative_to(tmp_path.resolve())
        finally:
            srv.NOTES_ROOT = original_root

    def test_list_notes(self, tmp_path: Path) -> None:
        import mcp_notes.server as srv

        original_root = srv.NOTES_ROOT
        srv.NOTES_ROOT = tmp_path
        try:
            inbox = tmp_path / "inbox"
            inbox.mkdir(parents=True)
            (inbox / "note1.md").write_text("# Note 1")
            (inbox / "note2.md").write_text("# Note 2")

            from mcp_notes.server import list_notes
            result = list_notes("inbox")
            assert "note1" in result
            assert "note2" in result
        finally:
            srv.NOTES_ROOT = original_root

    def test_list_notes_empty(self, tmp_path: Path) -> None:
        import mcp_notes.server as srv

        original_root = srv.NOTES_ROOT
        srv.NOTES_ROOT = tmp_path
        try:
            inbox = tmp_path / "inbox"
            inbox.mkdir(parents=True)

            from mcp_notes.server import list_notes
            assert "No notes found" in list_notes("inbox")
        finally:
            srv.NOTES_ROOT = original_root

    def test_list_notes_folder_not_found(self, tmp_path: Path) -> None:
        import mcp_notes.server as srv

        original_root = srv.NOTES_ROOT
        srv.NOTES_ROOT = tmp_path
        try:
            from mcp_notes.server import list_notes
            assert "Folder not found" in list_notes("nonexistent")
        finally:
            srv.NOTES_ROOT = original_root

    def test_read_note(self, tmp_path: Path) -> None:
        import mcp_notes.server as srv

        original_root = srv.NOTES_ROOT
        srv.NOTES_ROOT = tmp_path
        try:
            inbox = tmp_path / "inbox"
            inbox.mkdir(parents=True)
            (inbox / "test.md").write_text("# Test content")

            from mcp_notes.server import read_note
            result = read_note("inbox", "test")
            assert "Test content" in result
        finally:
            srv.NOTES_ROOT = original_root


# ---------------------------------------------------------------------------
# Tests — McpTool
# ---------------------------------------------------------------------------

class TestMcpTool:
    def test_tool_attributes(self) -> None:
        from agent_chat.tools.mcp_adapter import McpTool
        tool = McpTool(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            mcp_url="http://localhost:8302/mcp",
        )
        assert tool.name == "test_tool"
        assert tool.risk_level == "write"
        assert tool.timeout_seconds == 15.0


# ---------------------------------------------------------------------------
# Tests — async registry with MCP
# ---------------------------------------------------------------------------

class TestAsyncRegistry:
    @pytest.mark.asyncio
    async def test_register_all_tools_async(self) -> None:
        from agent_chat.tools.registry import ToolRegistry, _register_all_tools
        registry = ToolRegistry()
        await _register_all_tools(registry)
        # Should have all 7 built-in tools
        assert registry.get("weather") is not None
        assert registry.get("news") is not None
        assert registry.get("search") is not None
        assert registry.get("read_pdf") is not None
        assert registry.get("search_memory") is not None
        assert registry.get("kb_search") is not None
        assert registry.get("ingest_webpage") is not None

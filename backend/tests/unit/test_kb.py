"""Tests for knowledge base — streaming upload, KB search tool, text chunking."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent_chat.tools.kb_search import KBSearchTool


# ---------------------------------------------------------------------------
# Tests — save_pdf_from_path
# ---------------------------------------------------------------------------

class TestSavePdfFromPath:
    @pytest.mark.asyncio
    async def test_move_to_storage(self, tmp_path: Path) -> None:
        from agent_chat.storage.pdf_store import save_pdf_from_path

        src = tmp_path / "tmp_upload"
        src.write_bytes(b"%PDF-1.4 test content")
        content_hash = hashlib.sha256(b"%PDF-1.4 test content").hexdigest()

        result = await save_pdf_from_path(str(tmp_path), content_hash, src)
        assert result == f"uploads/{content_hash[:2]}/{content_hash}.pdf"
        assert not src.exists()  # moved, not copied
        assert (tmp_path / result).exists()

    @pytest.mark.asyncio
    async def test_dedup_removes_src(self, tmp_path: Path) -> None:
        from agent_chat.storage.pdf_store import save_pdf_from_path

        content_hash = "abcdef1234567890" * 4  # fake 64-char hash
        # Create the destination first
        dest_dir = tmp_path / "uploads" / content_hash[:2]
        dest_dir.mkdir(parents=True)
        (dest_dir / f"{content_hash}.pdf").write_bytes(b"existing")

        src = tmp_path / "tmp_upload"
        src.write_bytes(b"duplicate")

        result = await save_pdf_from_path(str(tmp_path), content_hash, src)
        assert not src.exists()  # src cleaned up


# ---------------------------------------------------------------------------
# Tests — KBSearchTool
# ---------------------------------------------------------------------------

class TestKBSearchTool:
    def test_schema(self) -> None:
        tool = KBSearchTool()
        assert tool.name == "kb_search"
        assert tool.risk_level == "read"
        assert "query" in tool.parameters["properties"]
        assert "query" in tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_no_user_context(self) -> None:
        tool = KBSearchTool()
        result = await tool.execute({"query": "test"}, context=None)
        assert result["code"] == "NO_USER_CONTEXT"

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        mock_results = [
            {
                "source_title": "test.pdf",
                "source_type": "pdf",
                "content": "This is test content " * 10,
                "score": 0.95432,
                "metadata": {"page_number": 3},
            }
        ]
        tool = KBSearchTool()
        with patch("agent_chat.tools.kb_search.search_kb", new_callable=AsyncMock, return_value=mock_results):
            result = await tool.execute(
                {"query": "test query"},
                context={"user_id": "user123"},
            )

        assert result["query"] == "test query"
        assert len(result["results"]) == 1
        assert result["results"][0]["source_title"] == "test.pdf"
        assert result["results"][0]["relevance"] == 0.954
        assert result["results"][0]["page_number"] == 3

    @pytest.mark.asyncio
    async def test_content_truncated(self) -> None:
        long_content = "x" * 1000
        mock_results = [
            {
                "source_title": "doc.pdf",
                "source_type": "pdf",
                "content": long_content,
                "score": 0.8,
                "metadata": {},
            }
        ]
        tool = KBSearchTool()
        with patch("agent_chat.tools.kb_search.search_kb", new_callable=AsyncMock, return_value=mock_results):
            result = await tool.execute(
                {"query": "test"},
                context={"user_id": "user123"},
            )

        assert len(result["results"][0]["content"]) == 500

    @pytest.mark.asyncio
    async def test_limit_clamped(self) -> None:
        tool = KBSearchTool()
        with patch("agent_chat.tools.kb_search.search_kb", new_callable=AsyncMock, return_value=[]) as mock_search:
            await tool.execute(
                {"query": "test", "limit": 100},
                context={"user_id": "user123"},
            )
            # limit should be clamped to 10
            mock_search.assert_called_once_with(
                user_id="user123",
                query="test",
                limit=10,
                source_type=None,
            )


# ---------------------------------------------------------------------------
# Tests — kb_service ingest
# ---------------------------------------------------------------------------

class TestKBServiceIngest:
    @pytest.mark.asyncio
    async def test_ingest_pdf_to_kb(self) -> None:
        from agent_chat.services.kb_service import ingest_pdf_to_kb

        mock_chunks = [
            {"content": "Page 1 text", "page_number": 1},
            {"content": "Page 2 text", "page_number": 2},
        ]
        mock_embeddings = [[0.1] * 384, [0.2] * 384]

        with (
            patch("agent_chat.services.kb_service.get_file_chunks", new_callable=AsyncMock, return_value=mock_chunks),
            patch("agent_chat.services.kb_service.embed_texts", new_callable=AsyncMock, return_value=mock_embeddings),
            patch("agent_chat.services.kb_service.create_kb_items", new_callable=AsyncMock) as mock_create,
        ):
            count = await ingest_pdf_to_kb("file1", "user1", "hash1", "test.pdf")

        assert count == 2
        items = mock_create.call_args[0][0]
        assert len(items) == 2
        assert items[0]["source_type"] == "pdf"
        assert items[0]["source_title"] == "test.pdf"
        assert items[0]["chunk_index"] == 0
        assert items[0]["metadata"]["page_number"] == 1

    @pytest.mark.asyncio
    async def test_ingest_no_chunks(self) -> None:
        from agent_chat.services.kb_service import ingest_pdf_to_kb

        with patch("agent_chat.services.kb_service.get_file_chunks", new_callable=AsyncMock, return_value=[]):
            count = await ingest_pdf_to_kb("file1", "user1", "hash1", "test.pdf")

        assert count == 0


# ---------------------------------------------------------------------------
# Tests — registry includes kb_search
# ---------------------------------------------------------------------------

class TestRegistryKBSearch:
    @pytest.mark.asyncio
    async def test_kb_search_registered(self) -> None:
        from agent_chat.tools.registry import ToolRegistry, _register_all_tools
        registry = ToolRegistry()
        await _register_all_tools(registry)
        assert registry.get("kb_search") is not None
        assert registry.get("kb_search").name == "kb_search"

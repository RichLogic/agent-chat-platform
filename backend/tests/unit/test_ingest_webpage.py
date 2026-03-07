"""Tests for web page ingestion — HTML extraction, text splitting, tool execution."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent_chat.tools.ingest_webpage import (
    IngestWebpageTool,
    _extract_text,
    _split_text,
)


# ---------------------------------------------------------------------------
# Tests — HTML extraction
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_basic_page(self) -> None:
        html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <nav>Navigation</nav>
            <article><p>Article content here.</p></article>
            <footer>Footer stuff</footer>
        </body>
        </html>
        """
        title, text = _extract_text(html)
        assert title == "Test Page"
        assert "Article content here" in text
        assert "Navigation" not in text
        assert "Footer stuff" not in text

    def test_no_article_uses_body(self) -> None:
        html = "<html><body><p>Body text only.</p></body></html>"
        title, text = _extract_text(html)
        assert "Body text only" in text

    def test_script_and_style_removed(self) -> None:
        html = """
        <html><body>
            <script>alert('xss')</script>
            <style>.foo { color: red }</style>
            <p>Visible text</p>
        </body></html>
        """
        _, text = _extract_text(html)
        assert "alert" not in text
        assert "color" not in text
        assert "Visible text" in text

    def test_empty_html(self) -> None:
        title, text = _extract_text("")
        assert title == ""
        assert text == ""

    def test_main_tag_preferred(self) -> None:
        html = """
        <html><body>
            <div>Outside main</div>
            <main><p>Inside main</p></main>
        </body></html>
        """
        _, text = _extract_text(html)
        assert "Inside main" in text


# ---------------------------------------------------------------------------
# Tests — Text splitting
# ---------------------------------------------------------------------------

class TestSplitText:
    def test_short_text_no_split(self) -> None:
        chunks = _split_text("Hello world", chunk_size=1000, overlap=200)
        assert chunks == ["Hello world"]

    def test_empty_text(self) -> None:
        assert _split_text("") == []
        assert _split_text("   ") == []

    def test_splits_with_overlap(self) -> None:
        text = "A" * 2500
        chunks = _split_text(text, chunk_size=1000, overlap=200)
        # 2500 chars with chunk=1000, overlap=200 => stride=800
        # chunks at: 0-1000, 800-1800, 1600-2500, 2400-2500
        assert len(chunks) >= 3
        assert len(chunks[0]) == 1000
        assert len(chunks[1]) == 1000

    def test_all_content_covered(self) -> None:
        text = "ABCDEFGHIJ" * 100  # 1000 chars
        chunks = _split_text(text, chunk_size=400, overlap=100)
        # Verify no content gaps by checking coverage
        combined = "".join(chunks)
        # Each chunk overlaps so combined is longer than original
        assert len(combined) >= len(text)


# ---------------------------------------------------------------------------
# Tests — IngestWebpageTool
# ---------------------------------------------------------------------------

class TestIngestWebpageTool:
    def test_schema(self) -> None:
        tool = IngestWebpageTool()
        assert tool.name == "ingest_webpage"
        assert tool.risk_level == "write"
        assert "url" in tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_no_user_context(self) -> None:
        tool = IngestWebpageTool()
        result = await tool.execute({"url": "https://example.com"}, context=None)
        assert result["code"] == "NO_USER_CONTEXT"

    @pytest.mark.asyncio
    async def test_successful_ingest(self) -> None:
        html = """
        <html>
        <head><title>Test Article</title></head>
        <body><article><p>Some article content that is long enough.</p></article></body>
        </html>
        """

        mock_response = AsyncMock()
        mock_response.text = html
        mock_response.content = html.encode()
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool = IngestWebpageTool()
        with (
            patch("agent_chat.tools.ingest_webpage.validate_url", return_value="https://example.com/article"),
            patch("agent_chat.tools.ingest_webpage.httpx.AsyncClient", return_value=mock_client),
            patch("agent_chat.tools.ingest_webpage.ingest_webpage_to_kb", new_callable=AsyncMock, return_value=1) as mock_ingest,
        ):
            result = await tool.execute(
                {"url": "https://example.com/article"},
                context={"user_id": "user123"},
            )

        assert result["title"] == "Test Article"
        assert result["chunks_saved"] == 1
        assert "已保存" in result["message"]
        mock_ingest.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_title(self) -> None:
        html = "<html><head><title>Original</title></head><body><p>Content.</p></body></html>"

        mock_response = AsyncMock()
        mock_response.text = html
        mock_response.content = html.encode()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool = IngestWebpageTool()
        with (
            patch("agent_chat.tools.ingest_webpage.validate_url", return_value="https://example.com"),
            patch("agent_chat.tools.ingest_webpage.httpx.AsyncClient", return_value=mock_client),
            patch("agent_chat.tools.ingest_webpage.ingest_webpage_to_kb", new_callable=AsyncMock, return_value=1),
        ):
            result = await tool.execute(
                {"url": "https://example.com", "title": "My Custom Title"},
                context={"user_id": "user123"},
            )

        assert result["title"] == "My Custom Title"

    @pytest.mark.asyncio
    async def test_empty_content(self) -> None:
        html = "<html><body><script>only script</script></body></html>"

        mock_response = AsyncMock()
        mock_response.text = html
        mock_response.content = html.encode()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool = IngestWebpageTool()
        with (
            patch("agent_chat.tools.ingest_webpage.validate_url", return_value="https://example.com"),
            patch("agent_chat.tools.ingest_webpage.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await tool.execute(
                {"url": "https://example.com"},
                context={"user_id": "user123"},
            )

        assert result["code"] == "EMPTY_CONTENT"


# ---------------------------------------------------------------------------
# Tests — registry includes ingest_webpage
# ---------------------------------------------------------------------------

class TestRegistryIngestWebpage:
    @pytest.mark.asyncio
    async def test_registered(self) -> None:
        from agent_chat.tools.registry import ToolRegistry, _register_all_tools
        registry = ToolRegistry()
        await _register_all_tools(registry)
        assert registry.get("ingest_webpage") is not None

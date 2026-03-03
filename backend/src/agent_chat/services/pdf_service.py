"""PDF parsing service — extracts Markdown content from PDF files."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from agent_chat.db.repository import create_file_chunks, update_file_parse_status
from agent_chat.storage.pdf_store import get_pdf_path

logger = structlog.get_logger()


def _parse_pdf_sync(file_path: str) -> list[dict]:
    """Synchronous PDF-to-Markdown parsing (runs in a thread)."""
    import pymupdf4llm

    return pymupdf4llm.to_markdown(file_path, page_chunks=True)


async def parse_pdf_to_chunks(
    file_id: str,
    data_dir: str,
    storage_path: str,
    content_hash: str,
    user_id: str | None = None,
    filename: str | None = None,
) -> None:
    """Parse a PDF file and store page chunks in MongoDB.

    Designed to be called via asyncio.create_task() as a background job.
    When user_id and filename are provided, also ingests chunks into the KB.
    """
    await update_file_parse_status(file_id, "parsing")
    try:
        pdf_path = get_pdf_path(data_dir, storage_path)
        pages = await asyncio.to_thread(_parse_pdf_sync, str(pdf_path))

        now = datetime.now(timezone.utc)
        chunks = [
            {
                "content_hash": content_hash,
                "page_number": i + 1,
                "content": page.get("text", ""),
                "char_count": len(page.get("text", "")),
                "created_at": now,
            }
            for i, page in enumerate(pages)
        ]

        await create_file_chunks(chunks)
        await update_file_parse_status(file_id, "done", page_count=len(chunks))
        logger.info("pdf_parsed", file_id=file_id, pages=len(chunks))

        # Ingest into knowledge base (non-blocking background task)
        if user_id and filename:
            try:
                from agent_chat.services.kb_service import ingest_pdf_to_kb
                await ingest_pdf_to_kb(file_id, user_id, content_hash, filename)
            except Exception as kb_err:
                logger.warning("kb_ingest_failed", file_id=file_id, error=str(kb_err))

    except Exception as e:
        logger.error("pdf_parse_failed", file_id=file_id, error=str(e))
        await update_file_parse_status(file_id, "failed")

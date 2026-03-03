"""Knowledge base ingestion and search service."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from agent_chat.db.repository import (
    create_kb_items,
    delete_kb_items_by_source,
    get_file_chunks,
    search_kb_vector,
)
from agent_chat.services.embedding_service import embed_text, embed_texts

logger = structlog.get_logger()


async def ingest_pdf_to_kb(
    file_id: str,
    user_id: str,
    content_hash: str,
    filename: str,
) -> int:
    """Embed parsed PDF chunks and store in the knowledge base.

    Returns the number of KB items created.
    """
    chunks = await get_file_chunks(content_hash)
    if not chunks:
        logger.warning("kb_ingest_no_chunks", file_id=file_id)
        return 0

    texts = [c["content"] for c in chunks]
    embeddings = await embed_texts(texts)

    now = datetime.now(timezone.utc)
    kb_docs = [
        {
            "user_id": user_id,
            "source_type": "pdf",
            "source_id": file_id,
            "source_title": filename,
            "chunk_index": i,
            "content": chunk["content"],
            "embedding": emb,
            "metadata": {"page_number": chunk.get("page_number")},
            "created_at": now,
        }
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    await create_kb_items(kb_docs)
    logger.info("kb_pdf_ingested", file_id=file_id, chunks=len(kb_docs))
    return len(kb_docs)


async def ingest_webpage_to_kb(
    user_id: str,
    url: str,
    title: str,
    chunks: list[str],
) -> int:
    """Embed webpage text chunks and store in the knowledge base.

    Re-ingestion is idempotent: deletes previous items for the same URL first.
    Returns the number of KB items created.
    """
    await delete_kb_items_by_source(url)

    if not chunks:
        return 0

    embeddings = await embed_texts(chunks)
    now = datetime.now(timezone.utc)
    kb_docs = [
        {
            "user_id": user_id,
            "source_type": "webpage",
            "source_id": url,
            "source_title": title,
            "chunk_index": i,
            "content": text,
            "embedding": emb,
            "metadata": {"url": url},
            "created_at": now,
        }
        for i, (text, emb) in enumerate(zip(chunks, embeddings))
    ]

    await create_kb_items(kb_docs)
    logger.info("kb_webpage_ingested", url=url, chunks=len(kb_docs))
    return len(kb_docs)


async def search_kb(
    user_id: str,
    query: str,
    limit: int = 5,
    source_type: str | None = None,
) -> list[dict]:
    """Search the knowledge base by semantic similarity."""
    query_embedding = await embed_text(query)
    return await search_kb_vector(user_id, query_embedding, limit, source_type)

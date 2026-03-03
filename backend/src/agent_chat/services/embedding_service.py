"""Local embedding service using sentence-transformers."""

from __future__ import annotations

import asyncio

import structlog

from agent_chat.config import get_settings

logger = structlog.get_logger()

_model = None


def _get_model():
    """Lazily load the SentenceTransformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        _model = SentenceTransformer(settings.embedding_model)
        logger.info("embedding_model_loaded", model=settings.embedding_model)
    return _model


async def embed_text(text: str) -> list[float]:
    """Embed a single text string. Runs in a thread to avoid blocking the event loop."""
    model = _get_model()
    result = await asyncio.to_thread(model.encode, text)
    return result.tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a batch."""
    model = _get_model()
    results = await asyncio.to_thread(model.encode, texts)
    return [r.tolist() for r in results]

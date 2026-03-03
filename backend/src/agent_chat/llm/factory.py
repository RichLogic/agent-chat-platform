"""LLM provider factory with fallback support."""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog

from agent_chat.config import Settings
from agent_chat.llm.provider import ChatResponse, LLMProvider, StreamChunk

logger = structlog.get_logger()


class FallbackProvider:
    """Wraps two LLMProvider instances; falls back to secondary on exception."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None):
        self.primary = primary
        self.fallback = fallback
        self.provider_name = primary.provider_name
        self.model = primary.model
        self._used_fallback = False

    @property
    def used_fallback(self) -> bool:
        return self._used_fallback

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[StreamChunk]:
        try:
            async for chunk in self.primary.stream_chat(messages):
                yield chunk
        except Exception as e:
            if not self.fallback:
                raise
            logger.warning(
                "primary_provider_failed",
                provider=self.primary.provider_name,
                error=str(e),
            )
            self._used_fallback = True
            self.provider_name = self.fallback.provider_name
            self.model = self.fallback.model
            async for chunk in self.fallback.stream_chat(messages):
                yield chunk

    async def chat(self, messages: list[dict]) -> ChatResponse:
        try:
            return await self.primary.chat(messages)
        except Exception as e:
            if not self.fallback:
                raise
            logger.warning(
                "primary_provider_failed_chat",
                provider=self.primary.provider_name,
                error=str(e),
            )
            self._used_fallback = True
            return await self.fallback.chat(messages)


def _build_provider(name: str, settings: Settings) -> LLMProvider:
    if name == "kimi":
        return LLMProvider(
            api_key=settings.kimi_api_key,
            base_url=settings.kimi_base_url,
            model=settings.kimi_model,
            provider_name="kimi",
        )
    return LLMProvider(
        api_key=settings.poe_api_key,
        base_url=settings.poe_base_url,
        model=settings.poe_model,
        provider_name="poe",
    )


def create_provider(settings: Settings) -> FallbackProvider:
    """Create a provider with optional fallback."""
    primary_name = settings.llm_provider
    fallback_name = "kimi" if primary_name != "kimi" else "poe"

    primary = _build_provider(primary_name, settings)

    # Only create fallback if it has credentials
    fallback_key = settings.kimi_api_key if fallback_name == "kimi" else settings.poe_api_key
    fallback = _build_provider(fallback_name, settings) if fallback_key else None

    return FallbackProvider(primary, fallback)

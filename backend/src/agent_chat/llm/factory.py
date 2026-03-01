"""LLM provider factory."""

from __future__ import annotations

from agent_chat.config import Settings
from agent_chat.llm.provider import LLMProvider


def create_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "kimi":
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

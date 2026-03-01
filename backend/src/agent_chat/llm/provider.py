"""LLM provider abstraction using OpenAI-compatible API."""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
from collections.abc import AsyncIterator

import httpx
from openai import AsyncOpenAI


@dataclass
class StreamChunk:
    content: str = ""
    usage: dict | None = None


@dataclass
class ChatResponse:
    content: str
    usage: dict | None = None


class LLMProvider:
    def __init__(self, api_key: str, base_url: str, model: str, provider_name: str):
        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.load_default_certs()
        http_client = httpx.AsyncClient(proxy=proxy, verify=ssl_ctx)
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
        self.model = model
        self.provider_name = provider_name

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[StreamChunk]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in response:
            if not chunk.choices and chunk.usage:
                yield StreamChunk(
                    usage={
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                )
                continue
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield StreamChunk(content=delta.content)

    async def chat(self, messages: list[dict]) -> ChatResponse:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        msg = response.choices[0].message
        content = msg.content or ""
        return ChatResponse(content=content, usage=usage)

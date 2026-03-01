"""Conversation title generation service."""

from __future__ import annotations

import json
from pathlib import Path

from agent_chat.config import Settings
from agent_chat.llm.factory import create_provider


def _load_title_prompt() -> dict:
    """Load the title generation prompt from prompts/system.json."""
    prompts_file = Path(__file__).parent.parent / "prompts" / "system.json"
    with open(prompts_file) as f:
        prompts = json.load(f)
    return prompts["title_generation"]


async def generate_title(user_content: str, assistant_content: str, settings: Settings) -> str:
    """Use LLM to generate a short conversation title."""
    provider = create_provider(settings)
    messages = [
        _load_title_prompt(),
        {
            "role": "user",
            "content": f"User message: {user_content}\n\nAssistant response: {assistant_content[:500]}",
        },
    ]
    response = await provider.chat(messages)
    return response.content.strip().strip('"').strip("'")

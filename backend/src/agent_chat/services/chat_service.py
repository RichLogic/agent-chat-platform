"""Core chat streaming service with tool calling support."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import structlog

from agent_chat.config import Settings
from agent_chat.db.repository import (
    count_messages,
    create_message,
    create_run,
    fail_run,
    finish_run,
    get_conversation,
    get_files_by_ids,
    list_messages,
    update_conversation_title,
)
from agent_chat.llm.factory import create_provider
from agent_chat.services.title_service import generate_title
from agent_chat.storage.file_store import write_event
from agent_chat.tools.registry import get_registry

logger = structlog.get_logger()


def _load_prompts() -> dict:
    """Load all prompts from prompts/system.json."""
    prompts_file = Path(__file__).parent.parent / "prompts" / "system.json"
    with open(prompts_file) as f:
        return json.load(f)


def _make_event(event_type: str, data: dict) -> dict:
    return {
        "type": event_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def _build_tool_dispatch_prompt(prompts: dict) -> dict:
    """Build system prompt with tool schemas injected."""
    registry = get_registry()
    template = prompts["tool_dispatch"]["content"]
    content = template.replace("{tools_schema}", registry.generate_schema())
    return {"role": "system", "content": content}


def _try_parse_tool_call(text: str) -> dict | None:
    """Try to parse LLM output as a tool call JSON."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict) and "tool" in parsed and "arguments" in parsed:
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return None


async def _build_file_hint(file_ids: list[str]) -> str:
    """Build an attachment hint string for the LLM, listing uploaded files."""
    files = await get_files_by_ids(file_ids)
    if not files:
        return ""
    parts = []
    for f in files:
        page_info = f"{f['page_count']}页" if f.get("page_count") else "解析中"
        parts.append(f"{f['original_filename']} (file_id: {f['id']}, {page_info})")
    return "\n[附件: " + ", ".join(parts) + "] — 使用 read_pdf tool 读取内容"


async def _enrich_message_content(msg: dict) -> str:
    """If a message has file_ids, append the file hint to its content."""
    content = msg["content"]
    fids = msg.get("file_ids")
    if fids:
        hint = await _build_file_hint(fids)
        if hint:
            content += hint
    return content


async def handle_chat_stream(
    conversation_id: str,
    user_content: str,
    user_id: str,
    settings: Settings,
    file_ids: list[str] | None = None,
) -> AsyncIterator[dict]:
    """Yields SSE event dicts for the chat stream, with tool calling support."""
    # Verify conversation ownership
    conversation = await get_conversation(conversation_id)
    if not conversation or conversation.get("user_id") != user_id:
        yield _make_event("error", {"message": "Conversation not found"})
        return

    # Save user message
    await create_message(conversation_id, "user", user_content, file_ids=file_ids)

    # Ingest user message into memory (background, non-blocking)
    from agent_chat.services.memory_service import ingest_user_message
    asyncio.create_task(ingest_user_message(user_id, conversation_id, user_content))

    # Create provider and run
    provider = create_provider(settings)
    run_id = uuid.uuid4().hex
    events_file = str(Path(settings.data_dir) / "runs" / run_id / "events.jsonl")

    await create_run(
        run_id=run_id,
        conversation_id=conversation_id,
        user_id=user_id,
        provider=provider.provider_name,
        model=provider.model,
        events_file=events_file,
    )

    # Yield run.start
    start_event = _make_event("run.start", {
        "run_id": run_id,
        "provider": provider.provider_name,
        "model": provider.model,
    })
    yield start_event
    await write_event(settings.data_dir, run_id, start_event)

    try:
        # Load history and build messages array
        history = await list_messages(conversation_id)
        prompts = _load_prompts()
        system_prompt = _build_tool_dispatch_prompt(prompts)
        messages = [system_prompt]
        for msg in history:
            content = await _enrich_message_content(msg)
            messages.append({"role": msg["role"], "content": content})

        # Emit messages.sent for the first LLM call
        msgs_sent_event = _make_event("messages.sent", {
            "call_index": 0,
            "messages": messages,
        })
        await write_event(settings.data_dir, run_id, msgs_sent_event)

        # Stream first LLM call with tool-call detection:
        # - If first non-whitespace char is '{', buffer everything to check for tool call
        # - Otherwise, stream text.delta events directly
        accumulated_content = ""
        token_usage = None
        maybe_tool = None  # None = undecided, True = buffering, False = streaming
        flushed_events: list[dict] = []

        async for chunk in provider.stream_chat(messages):
            if chunk.content:
                accumulated_content += chunk.content

                if maybe_tool is None:
                    # Check first non-whitespace char
                    stripped = accumulated_content.lstrip()
                    if not stripped:
                        continue  # Only whitespace so far
                    maybe_tool = stripped[0] == "{"

                if not maybe_tool:
                    # Stream directly — emit this chunk's content
                    delta_event = _make_event("text.delta", {"content": chunk.content})
                    yield delta_event
                    await write_event(settings.data_dir, run_id, delta_event)

            if chunk.usage:
                token_usage = chunk.usage

        # If we never decided (empty response), treat as non-tool
        if maybe_tool is None:
            maybe_tool = False

        # Check for tool call
        tool_call = _try_parse_tool_call(accumulated_content) if maybe_tool else None

        if tool_call:
            tool_name = tool_call["tool"]
            tool_args = tool_call["arguments"]

            # Emit tool.call event
            tool_call_event = _make_event("tool.call", {
                "name": tool_name,
                "arguments": tool_args,
            })
            yield tool_call_event
            await write_event(settings.data_dir, run_id, tool_call_event)

            # Execute the tool
            registry = get_registry()
            tool_result = await registry.execute(
                tool_name, tool_args, context={"user_id": user_id}
            )

            # Emit tool.result event
            tool_result_event = _make_event("tool.result", {
                "name": tool_name,
                "result": tool_result,
            })
            yield tool_result_event
            await write_event(settings.data_dir, run_id, tool_result_event)

            # Second LLM call — stream response based on tool result
            tool_response_prompt = {
                "role": "system",
                "content": prompts["tool_response"]["content"],
            }
            second_messages = [tool_response_prompt]
            for msg in history:
                content = await _enrich_message_content(msg)
                second_messages.append({"role": msg["role"], "content": content})
            second_messages.append({
                "role": "assistant",
                "content": f"[Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})]\n\n{json.dumps(tool_result, ensure_ascii=False, indent=2)}",
            })
            second_messages.append({
                "role": "user",
                "content": "请根据上面的工具结果回答我的问题。",
            })

            # Emit messages.sent for the second LLM call
            msgs_sent_event_2 = _make_event("messages.sent", {
                "call_index": 1,
                "messages": second_messages,
            })
            await write_event(settings.data_dir, run_id, msgs_sent_event_2)

            accumulated_content = ""
            token_usage_2 = None

            async for chunk in provider.stream_chat(second_messages):
                if chunk.content:
                    accumulated_content += chunk.content
                    delta_event = _make_event("text.delta", {"content": chunk.content})
                    yield delta_event
                    await write_event(settings.data_dir, run_id, delta_event)
                if chunk.usage:
                    token_usage_2 = chunk.usage

            # Merge token usage from both calls
            if token_usage and token_usage_2:
                token_usage = {
                    "prompt_tokens": token_usage["prompt_tokens"] + token_usage_2["prompt_tokens"],
                    "completion_tokens": token_usage["completion_tokens"] + token_usage_2["completion_tokens"],
                    "total_tokens": token_usage["total_tokens"] + token_usage_2["total_tokens"],
                }
            elif token_usage_2:
                token_usage = token_usage_2

        elif maybe_tool:
            # Looked like a tool call (started with {) but wasn't valid JSON tool call
            # Emit the buffered content as a single text.delta
            if accumulated_content:
                delta_event = _make_event("text.delta", {"content": accumulated_content})
                yield delta_event
                await write_event(settings.data_dir, run_id, delta_event)

        # Save assistant message
        await create_message(
            conversation_id,
            "assistant",
            accumulated_content,
            provider=provider.provider_name,
            model=provider.model,
            run_id=run_id,
            token_usage=token_usage,
        )

        # Finish run
        await finish_run(run_id, token_usage)

        finish_event = _make_event("run.finish", {
            "finish_reason": "stop",
            "token_usage": token_usage,
        })
        yield finish_event
        await write_event(settings.data_dir, run_id, finish_event)

        # If first message pair, generate title
        msg_count = await count_messages(conversation_id)
        if msg_count <= 2:
            try:
                title = await generate_title(user_content, accumulated_content, settings)
                await update_conversation_title(conversation_id, title)
                yield _make_event("conversation.title", {"title": title})
            except Exception as e:
                logger.warning("title_generation_failed", error=str(e))

    except Exception as e:
        logger.error("chat_stream_error", error=str(e))
        error_event = _make_event("error", {"message": str(e)})
        yield error_event
        await write_event(settings.data_dir, run_id, error_event)
        await fail_run(run_id)

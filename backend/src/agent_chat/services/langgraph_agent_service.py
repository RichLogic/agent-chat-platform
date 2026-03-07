"""LangGraph Agent service — plan-and-execute mode with checkpoint/resume.

This module provides ``handle_chat_stream_langgraph``, an async generator
that mirrors the signature and event contract of the existing
``handle_chat_stream`` but uses a LangGraph graph internally.

Key design choices:
- SSE events are emitted through LangGraph's custom stream writer
  (``stream_mode=["custom"]``).  The outer async-for loop yields them to
  the client and writes them to events.jsonl — identical to the original flow.
- Checkpoint uses AsyncSqliteSaver with ``thread_id = conversation_id`` so
  state survives server restarts.
- Resume detection: before running the graph we check ``graph.aget_state``
  for a pending interrupt.  If one exists we pass ``Command(resume=...)``
  instead of a fresh input dict.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import structlog

from agent_chat.config import Settings
from agent_chat.db.repository import (
    count_messages,
    create_message,
    create_run,
    fail_run,
    finish_run,
    get_conversation,
    list_messages,
    update_conversation_title,
)
from agent_chat.llm.factory import create_provider
from agent_chat.services.title_service import generate_title
from agent_chat.storage.file_store import write_event
from agent_chat.tools.registry import get_registry

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Checkpointer singleton
# ---------------------------------------------------------------------------
_checkpointer = None


async def _get_checkpointer(settings: Settings):
    """Lazily initialise the AsyncSqliteSaver singleton."""
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    db_path = settings.langgraph_checkpoint_db
    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = await aiosqlite.connect(db_path)
    _checkpointer = AsyncSqliteSaver(conn)
    await _checkpointer.setup()
    logger.info("langgraph_checkpointer_ready", db=db_path)
    return _checkpointer


# ---------------------------------------------------------------------------
# Event helper (same structure as chat_service._make_event)
# ---------------------------------------------------------------------------

def _make_event(event_type: str, data: dict) -> dict:
    return {
        "type": event_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


# ---------------------------------------------------------------------------
# File-hint helper (reuse logic from chat_service)
# ---------------------------------------------------------------------------

async def _build_file_hint(file_ids: list[str]) -> str:
    from agent_chat.db.repository import get_files_by_ids
    files = await get_files_by_ids(file_ids)
    if not files:
        return ""
    parts = []
    for f in files:
        page_info = f"{f['page_count']}页" if f.get("page_count") else "解析中"
        parts.append(f"{f['original_filename']} (file_id: {f['id']}, {page_info})")
    return "\n[附件: " + ", ".join(parts) + "] — 使用 read_pdf tool 读取内容"


async def _enrich_message_content(msg: dict) -> str:
    content = msg["content"]
    fids = msg.get("file_ids")
    if fids:
        hint = await _build_file_hint(fids)
        if hint:
            content += hint
    return content


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def handle_chat_stream_langgraph(
    conversation_id: str,
    user_content: str,
    user_id: str,
    settings: Settings,
    file_ids: list[str] | None = None,
) -> AsyncIterator[dict]:
    """Yields SSE event dicts using the LangGraph plan-execute-synthesize graph.

    The event types are identical to handle_chat_stream:
      run.start, text.delta, tool.call, tool.result, run.finish,
      conversation.title, error
    """
    # 1. Verify conversation ownership
    conversation = await get_conversation(conversation_id)
    if not conversation or conversation.get("user_id") != user_id:
        yield _make_event("error", {"message": "Conversation not found"})
        return

    # 2. Save user message
    await create_message(conversation_id, "user", user_content, file_ids=file_ids)

    # 3. Ingest into memory (background, non-blocking)
    from agent_chat.services.memory_service import ingest_user_message
    asyncio.create_task(ingest_user_message(user_id, conversation_id, user_content))

    # 4. Create provider and run
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

    # 5. Yield run.start
    start_event = _make_event("run.start", {
        "run_id": run_id,
        "provider": provider.provider_name,
        "model": provider.model,
    })
    yield start_event
    await write_event(settings.data_dir, run_id, start_event)

    try:
        # 6. Load conversation history
        history = await list_messages(conversation_id)
        messages = []
        for msg in history:
            content = await _enrich_message_content(msg)
            messages.append({"role": msg["role"], "content": content})

        # 7. Initialise checkpointer and graph
        checkpointer = await _get_checkpointer(settings)

        from agent_chat.agents.plan_execute import build_graph
        graph = build_graph(checkpointer=checkpointer)

        registry = await get_registry()

        langgraph_config = {
            "configurable": {
                "thread_id": conversation_id,  # stable thread_id for checkpoint
                "provider": provider,
                "registry": registry,
                "user_id": user_id,
                "run_id": run_id,
            }
        }

        # 8. Detect pending interrupt (resume support)
        # If the graph was previously interrupted (e.g. waiting for user
        # confirmation), we resume it with the user's new message as the
        # resume value.  Otherwise we start a fresh run.
        from langgraph.types import Command

        graph_state = await graph.aget_state(langgraph_config)
        is_resuming = bool(
            graph_state
            and graph_state.values
            and getattr(graph_state, "tasks", None)
            and any(
                getattr(t, "interrupts", None)
                for t in graph_state.tasks
            )
        )

        if is_resuming:
            logger.info(
                "langgraph_resume",
                conversation_id=conversation_id,
                resume_content=user_content[:50],
            )
            graph_input = Command(resume=user_content)
        else:
            graph_input = {
                "messages": messages,
                "user_content": user_content,
                "plan": None,
                "tool_calls": [],
                "tool_results": [],
                "final_text": "",
            }

        # 9. Stream the graph — custom events are our SSE events
        final_text = ""
        async for chunk in graph.astream(
            graph_input,
            langgraph_config,
            stream_mode=["custom", "updates"],
        ):
            # stream_mode=["custom", "updates"] yields (mode, data) tuples
            mode, data = chunk

            if mode == "custom":
                # data is an SSE event dict emitted by nodes via writer()
                yield data
                await write_event(settings.data_dir, run_id, data)
            elif mode == "updates":
                # data is a dict of {node_name: state_update}
                # Extract final_text from synthesizer output
                if isinstance(data, dict):
                    for node_name, update in data.items():
                        if isinstance(update, dict) and "final_text" in update:
                            final_text = update["final_text"]

        # If we didn't capture final_text from updates, try to get it from state
        if not final_text:
            final_state = await graph.aget_state(langgraph_config)
            if final_state and final_state.values:
                final_text = final_state.values.get("final_text", "")

        # 10. Save assistant message
        await create_message(
            conversation_id,
            "assistant",
            final_text,
            provider=provider.provider_name,
            model=provider.model,
            run_id=run_id,
        )

        # 11. Finish run
        await finish_run(run_id, None)

        finish_event = _make_event("run.finish", {
            "finish_reason": "stop",
            "token_usage": None,
        })
        yield finish_event
        await write_event(settings.data_dir, run_id, finish_event)

        # 12. Generate title for first message pair
        msg_count = await count_messages(conversation_id)
        if msg_count <= 2:
            try:
                title = await generate_title(user_content, final_text, settings)
                await update_conversation_title(conversation_id, title)
                yield _make_event("conversation.title", {"title": title})
            except Exception as e:
                logger.warning("title_generation_failed", error=str(e))

    except Exception as e:
        logger.error("langgraph_stream_error", error=str(e), exc_info=True)
        error_event = _make_event("error", {"message": str(e)})
        yield error_event
        await write_event(settings.data_dir, run_id, error_event)
        await fail_run(run_id)
    except BaseException:
        # CancelledError / GeneratorExit — client disconnected or server
        # is shutting down.  Mark the run as failed so it doesn't become
        # a zombie.
        logger.warning("langgraph_stream_cancelled", run_id=run_id)
        await fail_run(run_id)
        raise

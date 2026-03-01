"""End-to-end smoke tests for the chat API."""

from __future__ import annotations

import json

import httpx


async def collect_sse_events(response: httpx.Response) -> list[dict]:
    """Collect all SSE events from an httpx streaming response."""
    events = []
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    if buffer.strip().startswith("data: "):
        events.append(json.loads(buffer.strip()[6:]))
    return events


async def test_conversation_crud(client: httpx.AsyncClient):
    # Create
    resp = await client.post("/api/conversations")
    assert resp.status_code == 200
    conv = resp.json()
    assert "id" in conv
    assert conv["title"] == ""
    conv_id = conv["id"]

    # List — should include the new conversation
    resp = await client.get("/api/conversations")
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [c["id"] for c in items]
    assert conv_id in ids

    # Delete
    resp = await client.delete(f"/api/conversations/{conv_id}")
    assert resp.status_code == 204

    # List — should no longer include deleted conversation
    resp = await client.get("/api/conversations")
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [c["id"] for c in items]
    assert conv_id not in ids


async def test_full_chat_flow(client: httpx.AsyncClient):
    # 1. Create conversation
    resp = await client.post("/api/conversations")
    assert resp.status_code == 200
    conv_id = resp.json()["id"]

    # 2. Send chat message and collect SSE events
    async with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conv_id, "content": "你好"},
    ) as response:
        assert response.status_code == 200
        events = await collect_sse_events(response)

    # 3. Verify event sequence
    types = [e["type"] for e in events]
    assert types[0] == "run.start"
    assert "text.delta" in types
    assert "run.finish" in types

    # run.start should come first, run.finish after all text.delta
    start_idx = types.index("run.start")
    finish_idx = types.index("run.finish")
    delta_indices = [i for i, t in enumerate(types) if t == "text.delta"]
    assert start_idx < delta_indices[0]
    assert delta_indices[-1] < finish_idx

    # conversation.title should come after run.finish (first message pair)
    assert "conversation.title" in types
    title_idx = types.index("conversation.title")
    assert title_idx > finish_idx

    # Extract run_id from run.start
    run_id = events[start_idx]["data"]["run_id"]

    # 4. Verify messages persisted
    resp = await client.get(f"/api/conversations/{conv_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()["items"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "你好"
    assert messages[1]["role"] == "assistant"
    assert "Hello" in messages[1]["content"]

    # 5. Verify title updated
    resp = await client.get("/api/conversations")
    assert resp.status_code == 200
    items = resp.json()["items"]
    conv = next(c for c in items if c["id"] == conv_id)
    assert conv["title"] != ""


async def test_message_history(client: httpx.AsyncClient):
    # Create conversation
    resp = await client.post("/api/conversations")
    conv_id = resp.json()["id"]

    # First message
    async with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conv_id, "content": "First message"},
    ) as response:
        await collect_sse_events(response)

    # Second message
    async with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conv_id, "content": "Second message"},
    ) as response:
        await collect_sse_events(response)

    # Verify 4 messages: 2 user + 2 assistant
    resp = await client.get(f"/api/conversations/{conv_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()["items"]
    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"
    assert messages[3]["role"] == "assistant"

    # Verify chronological order
    for i in range(len(messages) - 1):
        assert messages[i]["created_at"] <= messages[i + 1]["created_at"]


async def test_replay_events(client: httpx.AsyncClient):
    # Create conversation and send a message
    resp = await client.post("/api/conversations")
    conv_id = resp.json()["id"]

    # Chat and capture events
    async with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": conv_id, "content": "Hello"},
    ) as response:
        original_events = await collect_sse_events(response)

    # Extract run_id
    run_start = next(e for e in original_events if e["type"] == "run.start")
    run_id = run_start["data"]["run_id"]

    # Replay events
    async with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.status_code == 200
        replayed = await collect_sse_events(response)

    # Replayed events should contain the same core events (start, deltas, finish)
    original_types = [e["type"] for e in original_events if e["type"] != "conversation.title"]
    replayed_types = [e["type"] for e in replayed]
    assert original_types == replayed_types

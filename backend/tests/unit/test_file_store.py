"""JSONL file store read/write tests."""

from __future__ import annotations

from agent_chat.storage.file_store import read_events, write_event


async def test_write_and_read(tmp_path):
    data_dir = str(tmp_path)
    run_id = "test-run-001"

    events = [
        {"type": "run.start", "data": {"run_id": run_id}},
        {"type": "text.delta", "data": {"content": "Hello"}},
        {"type": "run.finish", "data": {"finish_reason": "stop"}},
    ]
    for event in events:
        await write_event(data_dir, run_id, event)

    read_back = []
    async for evt in read_events(data_dir, run_id):
        read_back.append(evt)

    assert len(read_back) == 3
    assert read_back[0]["type"] == "run.start"
    assert read_back[1]["data"]["content"] == "Hello"
    assert read_back[2]["type"] == "run.finish"


async def test_read_nonexistent(tmp_path):
    data_dir = str(tmp_path)
    events = []
    async for evt in read_events(data_dir, "nonexistent-run"):
        events.append(evt)
    assert events == []

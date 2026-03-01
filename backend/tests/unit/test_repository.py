"""MongoDB repository CRUD tests using mongomock-motor."""

from __future__ import annotations

import asyncio

from agent_chat.db.repository import (
    count_messages,
    create_conversation,
    create_message,
    create_run,
    delete_conversation,
    finish_run,
    get_run,
    get_user,
    list_conversations,
    list_messages,
    upsert_user,
)


async def test_upsert_user_create(mock_db):
    user = await upsert_user(
        github_id=12345,
        github_login="testuser",
        display_name="Test User",
        avatar_url="https://example.com/avatar.png",
        email="test@example.com",
    )
    assert "id" in user
    assert user["github_login"] == "testuser"
    assert user["display_name"] == "Test User"


async def test_upsert_user_update(mock_db):
    user1 = await upsert_user(
        github_id=12345,
        github_login="testuser",
        display_name="Old Name",
        avatar_url="https://example.com/avatar.png",
        email="test@example.com",
    )
    user2 = await upsert_user(
        github_id=12345,
        github_login="testuser",
        display_name="New Name",
        avatar_url="https://example.com/avatar2.png",
        email="test2@example.com",
    )
    assert user1["id"] == user2["id"]
    assert user2["display_name"] == "New Name"
    assert user2["email"] == "test2@example.com"


async def test_get_user_found(mock_db):
    created = await upsert_user(
        github_id=99999,
        github_login="findme",
        display_name="Find Me",
        avatar_url="https://example.com/a.png",
        email="find@example.com",
    )
    found = await get_user(created["id"])
    assert found is not None
    assert found["github_login"] == "findme"


async def test_get_user_not_found(mock_db):
    result = await get_user("000000000000000000000099")
    assert result is None


async def test_create_conversation(mock_db):
    conv = await create_conversation("user-1")
    assert "id" in conv
    assert conv["title"] == ""
    assert conv["user_id"] == "user-1"


async def test_list_conversations_excludes_deleted(mock_db):
    conv1 = await create_conversation("user-1")
    conv2 = await create_conversation("user-1")

    await delete_conversation(conv1["id"], "user-1")

    convs = await list_conversations("user-1")
    ids = [c["id"] for c in convs]
    assert conv1["id"] not in ids
    assert conv2["id"] in ids


async def test_list_conversations_order(mock_db):
    c1 = await create_conversation("user-1")
    # Small delay to ensure different timestamps
    await asyncio.sleep(0.01)
    c2 = await create_conversation("user-1")
    await asyncio.sleep(0.01)
    c3 = await create_conversation("user-1")

    convs = await list_conversations("user-1")
    ids = [c["id"] for c in convs]
    # Most recent first
    assert ids == [c3["id"], c2["id"], c1["id"]]


async def test_create_and_list_messages(mock_db):
    conv = await create_conversation("user-1")

    await create_message(conv["id"], "user", "Hello")
    await asyncio.sleep(0.01)
    await create_message(conv["id"], "assistant", "Hi there!", provider="poe", model="test")
    await asyncio.sleep(0.01)
    await create_message(conv["id"], "user", "How are you?")

    msgs = await list_messages(conv["id"])
    assert len(msgs) == 3
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello"
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["role"] == "user"
    # Ascending order by created_at
    assert msgs[0]["created_at"] <= msgs[1]["created_at"] <= msgs[2]["created_at"]


async def test_run_lifecycle(mock_db):
    run = await create_run(
        run_id="run-001",
        conversation_id="conv-1",
        user_id="user-1",
        provider="poe",
        model="test-model",
        events_file="/data/runs/run-001/events.jsonl",
    )
    assert run["id"] == "run-001"
    assert run["status"] == "running"

    await finish_run("run-001", {"total_tokens": 100})

    finished = await get_run("run-001")
    assert finished["status"] == "finished"
    assert finished["token_usage"]["total_tokens"] == 100


async def test_count_messages(mock_db):
    conv = await create_conversation("user-1")

    for i in range(5):
        await create_message(conv["id"], "user", f"Message {i}")

    count = await count_messages(conv["id"])
    assert count == 5

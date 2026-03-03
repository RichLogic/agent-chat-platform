"""MongoDB repository CRUD tests using mongomock-motor."""

from __future__ import annotations

import asyncio

from agent_chat.db.repository import (
    cascade_delete_conversation,
    count_messages,
    create_conversation,
    create_file,
    create_memory,
    create_message,
    create_run,
    create_share,
    delete_conversation,
    finish_run,
    get_conversation_stats,
    get_run,
    get_share_by_conversation,
    get_user,
    get_user_conversation,
    get_user_stats,
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


# ---------------------------------------------------------------------------
# Cascade delete
# ---------------------------------------------------------------------------


async def test_cascade_delete_removes_share(mock_db):
    conv = await create_conversation("user-1")
    await create_share("tok-1", conv["id"], "user-1")

    # Verify share exists
    share = await get_share_by_conversation(conv["id"])
    assert share is not None

    await cascade_delete_conversation(conv["id"], "user-1")

    # Share should be gone
    share = await get_share_by_conversation(conv["id"])
    assert share is None


async def test_cascade_delete_compresses_memories(mock_db):
    conv = await create_conversation("user-1")
    await create_memory(
        user_id="user-1",
        conversation_id=conv["id"],
        content="test memory",
        embedding=[0.1] * 10,
        memory_type="message",
    )

    await cascade_delete_conversation(conv["id"], "user-1")

    # Memory should be marked as compressed
    from agent_chat.db.mongo import get_db

    db = get_db()
    mem = await db.memories.find_one({"conversation_id": conv["id"]})
    assert mem["is_compressed"] is True


# ---------------------------------------------------------------------------
# get_user_conversation
# ---------------------------------------------------------------------------


async def test_get_user_conversation_not_found_if_deleted(mock_db):
    conv = await create_conversation("user-1")
    await delete_conversation(conv["id"], "user-1")

    result = await get_user_conversation(conv["id"], "user-1")
    assert result is None


async def test_get_user_conversation_not_found_if_wrong_user(mock_db):
    conv = await create_conversation("user-1")

    result = await get_user_conversation(conv["id"], "user-2")
    assert result is None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def test_conversation_stats(mock_db):
    conv = await create_conversation("user-1")
    for i in range(3):
        await create_message(conv["id"], "user", f"msg {i}")
    await create_run(
        run_id="run-stat-1",
        conversation_id=conv["id"],
        user_id="user-1",
        provider="poe",
        model="test",
        events_file="/tmp/events.jsonl",
    )

    stats = await get_conversation_stats(conv["id"])
    assert stats["message_count"] == 3
    assert stats["run_count"] == 1


async def test_user_stats(mock_db):
    # Create 2 conversations (1 deleted)
    c1 = await create_conversation("user-1")
    c2 = await create_conversation("user-1")
    await delete_conversation(c2["id"], "user-1")

    # Create a file
    await create_file(
        uploaded_by="user-1",
        content_hash="abc123",
        original_filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        storage_path="/tmp/test.pdf",
    )

    # Create a memory
    await create_memory(
        user_id="user-1",
        conversation_id=c1["id"],
        content="test memory",
        embedding=[0.1] * 10,
        memory_type="message",
    )

    stats = await get_user_stats("user-1")
    assert stats["conversation_count"] == 1  # Only non-deleted
    assert stats["file_count"] == 1
    assert stats["memory_count"] == 1

"""All CRUD operations using motor."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId

from agent_chat.db.mongo import get_db


def _doc_to_dict(doc: dict) -> dict:
    """Convert a MongoDB document to a dict with 'id' string field."""
    if doc is None:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


async def upsert_user(
    github_id: int,
    github_login: str,
    display_name: str,
    avatar_url: str,
    email: str,
) -> dict:
    """Upsert a user by github_id and return the user dict."""
    db = get_db()
    now = datetime.now(timezone.utc)
    result = await db.users.find_one_and_update(
        {"github_id": github_id},
        {
            "$set": {
                "github_login": github_login,
                "display_name": display_name,
                "avatar_url": avatar_url,
                "email": email,
                "updated_at": now,
            },
            "$setOnInsert": {
                "github_id": github_id,
                "created_at": now,
            },
        },
        upsert=True,
        return_document=True,
    )
    return _doc_to_dict(result)


async def get_user(user_id: str) -> dict | None:
    """Get a user by id."""
    db = get_db()
    doc = await db.users.find_one({"_id": ObjectId(user_id)})
    if doc is None:
        return None
    return _doc_to_dict(doc)


async def create_conversation(user_id: str) -> dict:
    """Create a new conversation."""
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "title": "",
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.conversations.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_dict(doc)


async def list_conversations(user_id: str) -> list[dict]:
    """List all non-deleted conversations for a user, ordered by updated_at desc."""
    db = get_db()
    cursor = db.conversations.find(
        {"user_id": user_id, "is_deleted": False}
    ).sort("updated_at", -1)
    return [_doc_to_dict(doc) async for doc in cursor]


async def delete_conversation(conversation_id: str, user_id: str) -> None:
    """Soft delete a conversation."""
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.conversations.update_one(
        {"_id": ObjectId(conversation_id), "user_id": user_id},
        {"$set": {"is_deleted": True, "deleted_at": now}},
    )


async def get_conversation(conversation_id: str) -> dict | None:
    """Get a conversation by id."""
    db = get_db()
    doc = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
    if doc is None:
        return None
    return _doc_to_dict(doc)


async def update_conversation_title(conversation_id: str, title: str) -> None:
    """Update the title and updated_at of a conversation."""
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.conversations.update_one(
        {"_id": ObjectId(conversation_id)},
        {"$set": {"title": title, "updated_at": now}},
    )


async def create_message(
    conversation_id: str,
    role: str,
    content: str,
    provider: str | None = None,
    model: str | None = None,
    run_id: str | None = None,
    token_usage: dict | None = None,
) -> dict:
    """Create a new message in a conversation."""
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "provider": provider,
        "model": model,
        "run_id": run_id,
        "token_usage": token_usage,
        "created_at": now,
    }
    result = await db.messages.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_dict(doc)


async def list_messages(conversation_id: str) -> list[dict]:
    """List all messages in a conversation, ordered by created_at asc."""
    db = get_db()
    cursor = db.messages.find({"conversation_id": conversation_id}).sort("created_at", 1)
    return [_doc_to_dict(doc) async for doc in cursor]


async def create_run(
    run_id: str,
    conversation_id: str,
    user_id: str,
    provider: str,
    model: str,
    events_file: str,
) -> dict:
    """Create a new run record."""
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "_id": run_id,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "provider": provider,
        "model": model,
        "events_file": events_file,
        "status": "running",
        "token_usage": None,
        "created_at": now,
        "finished_at": None,
    }
    await db.runs.insert_one(doc)
    # For runs, _id is already a string, not ObjectId
    doc["id"] = doc.pop("_id")
    return doc


async def finish_run(run_id: str, token_usage: dict | None) -> None:
    """Mark a run as finished."""
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.runs.update_one(
        {"_id": run_id},
        {"$set": {"status": "finished", "finished_at": now, "token_usage": token_usage}},
    )


async def fail_run(run_id: str) -> None:
    """Mark a run as failed."""
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.runs.update_one(
        {"_id": run_id},
        {"$set": {"status": "failed", "finished_at": now}},
    )


async def get_run(run_id: str) -> dict | None:
    """Get a run by id."""
    db = get_db()
    doc = await db.runs.find_one({"_id": run_id})
    if doc is None:
        return None
    doc["id"] = doc.pop("_id")
    return doc


async def count_messages(conversation_id: str) -> int:
    """Count messages in a conversation."""
    db = get_db()
    return await db.messages.count_documents({"conversation_id": conversation_id})

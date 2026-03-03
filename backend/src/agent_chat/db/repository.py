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


async def cascade_delete_conversation(conversation_id: str, user_id: str) -> None:
    """Soft delete a conversation and clean up related records."""
    db = get_db()
    now = datetime.now(timezone.utc)
    # 1. Soft delete the conversation
    await db.conversations.update_one(
        {"_id": ObjectId(conversation_id), "user_id": user_id},
        {"$set": {"is_deleted": True, "deleted_at": now}},
    )
    # 2. Remove share link
    await db.shares.delete_one(
        {"conversation_id": conversation_id, "user_id": user_id}
    )
    # 3. Exclude memories from vector search
    await db.memories.update_many(
        {"conversation_id": conversation_id},
        {"$set": {"is_compressed": True}},
    )


async def get_conversation(conversation_id: str) -> dict | None:
    """Get a conversation by id."""
    db = get_db()
    doc = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
    if doc is None:
        return None
    return _doc_to_dict(doc)


async def get_user_conversation(conversation_id: str, user_id: str) -> dict | None:
    """Get a non-deleted conversation owned by the given user."""
    db = get_db()
    doc = await db.conversations.find_one({
        "_id": ObjectId(conversation_id),
        "user_id": user_id,
        "is_deleted": False,
    })
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
    file_ids: list[str] | None = None,
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
        "file_ids": file_ids,
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


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

async def find_file_by_hash(content_hash: str) -> dict | None:
    """Find a file by its content hash (for deduplication)."""
    db = get_db()
    doc = await db.files.find_one({"content_hash": content_hash})
    if doc is None:
        return None
    return _doc_to_dict(doc)


async def create_file(
    uploaded_by: str,
    content_hash: str,
    original_filename: str,
    mime_type: str,
    size_bytes: int,
    storage_path: str,
    page_count: int | None = None,
    parse_status: str = "pending",
) -> dict:
    """Create a file metadata record."""
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "uploaded_by": uploaded_by,
        "content_hash": content_hash,
        "original_filename": original_filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "storage_path": storage_path,
        "page_count": page_count,
        "parse_status": parse_status,
        "created_at": now,
    }
    result = await db.files.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_dict(doc)


async def get_file(file_id: str) -> dict | None:
    """Get a file by id."""
    db = get_db()
    doc = await db.files.find_one({"_id": ObjectId(file_id)})
    if doc is None:
        return None
    return _doc_to_dict(doc)


async def get_files_by_ids(file_ids: list[str]) -> list[dict]:
    """Get multiple files by their ids."""
    if not file_ids:
        return []
    db = get_db()
    object_ids = [ObjectId(fid) for fid in file_ids]
    cursor = db.files.find({"_id": {"$in": object_ids}})
    return [_doc_to_dict(doc) async for doc in cursor]


async def update_file_parse_status(
    file_id: str, status: str, page_count: int | None = None
) -> None:
    """Update parse status (and optionally page_count) of a file."""
    db = get_db()
    update: dict = {"$set": {"parse_status": status}}
    if page_count is not None:
        update["$set"]["page_count"] = page_count
    await db.files.update_one({"_id": ObjectId(file_id)}, update)


# ---------------------------------------------------------------------------
# File Chunks
# ---------------------------------------------------------------------------

async def create_file_chunks(chunks: list[dict]) -> None:
    """Bulk insert parsed file chunks."""
    if not chunks:
        return
    db = get_db()
    await db.file_chunks.insert_many(chunks)


async def get_file_chunks(
    content_hash: str, page_numbers: list[int] | None = None
) -> list[dict]:
    """Get parsed chunks for a file, optionally filtered by page numbers."""
    db = get_db()
    query: dict = {"content_hash": content_hash}
    if page_numbers:
        query["page_number"] = {"$in": page_numbers}
    cursor = db.file_chunks.find(query).sort("page_number", 1)
    return [_doc_to_dict(doc) async for doc in cursor]


# ---------------------------------------------------------------------------
# Shares
# ---------------------------------------------------------------------------

async def create_share(share_token: str, conversation_id: str, user_id: str) -> dict:
    """Create a share record for a conversation."""
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "share_token": share_token,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "created_at": now,
    }
    result = await db.shares.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_dict(doc)


async def get_share_by_token(share_token: str) -> dict | None:
    """Get a share by its token."""
    db = get_db()
    doc = await db.shares.find_one({"share_token": share_token})
    if doc is None:
        return None
    return _doc_to_dict(doc)


async def get_share_by_conversation(conversation_id: str) -> dict | None:
    """Get the share record for a conversation (if any)."""
    db = get_db()
    doc = await db.shares.find_one({"conversation_id": conversation_id})
    if doc is None:
        return None
    return _doc_to_dict(doc)


async def delete_share(conversation_id: str, user_id: str) -> bool:
    """Delete the share for a conversation. Returns True if deleted."""
    db = get_db()
    result = await db.shares.delete_one(
        {"conversation_id": conversation_id, "user_id": user_id}
    )
    return result.deleted_count > 0


async def list_runs_by_conversation(conversation_id: str) -> list[dict]:
    """List all runs for a conversation, ordered by created_at asc."""
    db = get_db()
    cursor = db.runs.find({"conversation_id": conversation_id}).sort("created_at", 1)
    docs = []
    async for doc in cursor:
        doc["id"] = doc.pop("_id")
        docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# Memories
# ---------------------------------------------------------------------------

async def create_memory(
    user_id: str,
    conversation_id: str,
    content: str,
    embedding: list[float],
    memory_type: str,
) -> dict:
    """Create a memory record with its embedding vector."""
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "content": content,
        "embedding": embedding,
        "memory_type": memory_type,  # "message" | "summary"
        "is_compressed": False,
        "created_at": now,
    }
    result = await db.memories.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_dict(doc)


async def search_memories_vector(
    user_id: str, query_embedding: list[float], limit: int = 5
) -> list[dict]:
    """Search memories using MongoDB Atlas vector search."""
    db = get_db()
    pipeline = [
        {
            "$vectorSearch": {
                "index": "memory_vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": 50,
                "limit": limit,
                "filter": {
                    "$and": [
                        {"user_id": {"$eq": user_id}},
                        {"is_compressed": {"$ne": True}},
                    ],
                },
            }
        },
        {
            "$project": {
                "content": 1,
                "memory_type": 1,
                "conversation_id": 1,
                "created_at": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    results = []
    async for doc in db.memories.aggregate(pipeline):
        doc["id"] = str(doc.pop("_id"))
        results.append(doc)
    return results


async def get_uncompressed_memories(conversation_id: str) -> list[dict]:
    """Get all uncompressed message memories for a conversation."""
    db = get_db()
    cursor = db.memories.find(
        {"conversation_id": conversation_id, "memory_type": "message", "is_compressed": False},
        {"embedding": 0},  # exclude large embedding field
    ).sort("created_at", 1)
    return [_doc_to_dict(doc) async for doc in cursor]


async def mark_memories_compressed(conversation_id: str) -> None:
    """Mark all message memories in a conversation as compressed."""
    db = get_db()
    await db.memories.update_many(
        {"conversation_id": conversation_id, "memory_type": "message", "is_compressed": False},
        {"$set": {"is_compressed": True}},
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

async def get_conversation_stats(conversation_id: str) -> dict:
    """Get aggregate stats for a conversation."""
    db = get_db()
    message_count = await db.messages.count_documents(
        {"conversation_id": conversation_id}
    )
    run_count = await db.runs.count_documents(
        {"conversation_id": conversation_id}
    )
    return {
        "message_count": message_count,
        "run_count": run_count,
    }


async def get_user_stats(user_id: str) -> dict:
    """Get aggregate stats for a user."""
    db = get_db()
    conversation_count = await db.conversations.count_documents(
        {"user_id": user_id, "is_deleted": False}
    )
    file_count = await db.files.count_documents({"uploaded_by": user_id})
    memory_count = await db.memories.count_documents(
        {"user_id": user_id, "is_compressed": False}
    )
    return {
        "conversation_count": conversation_count,
        "file_count": file_count,
        "memory_count": memory_count,
    }

"""MongoDB connection management using motor."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import structlog

logger = structlog.get_logger()

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db(uri: str, db_name: str) -> AsyncIOMotorDatabase:
    """Connect to MongoDB and return the database reference."""
    global _client, _db
    _client = AsyncIOMotorClient(uri)
    _db = _client[db_name]
    logger.info("mongodb_connected", db=db_name)
    return _db


async def disconnect_db() -> None:
    """Close the MongoDB client connection."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
        logger.info("mongodb_disconnected")


def get_db() -> AsyncIOMotorDatabase:
    """Return the current database reference."""
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all required indexes."""
    await db.users.create_index("github_id", unique=True)
    await db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
    await db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
    await db.runs.create_index("conversation_id")

    # File upload & PDF parsing
    await db.files.create_index("content_hash", unique=True)
    await db.files.create_index("uploaded_by")
    await db.file_chunks.create_index(
        [("content_hash", 1), ("page_number", 1)], unique=True
    )

    # Shares
    await db.shares.create_index("share_token", unique=True)
    await db.shares.create_index("conversation_id", unique=True)

    # Memories
    await db.memories.create_index([("user_id", 1), ("is_compressed", 1)])
    await db.memories.create_index("conversation_id")
    await _ensure_vector_search_index(db)

    # Knowledge base items
    await db.kb_items.create_index([("user_id", 1), ("source_type", 1)])
    await db.kb_items.create_index([("source_id", 1), ("chunk_index", 1)], unique=True)
    await _ensure_kb_vector_search_index(db)

    logger.info("mongodb_indexes_created")


async def _ensure_vector_search_index(db: AsyncIOMotorDatabase) -> None:
    """Create vector search index for memories collection (MongoDB Atlas Local)."""
    try:
        await db.command({
            "createSearchIndexes": "memories",
            "indexes": [{
                "name": "memory_vector_index",
                "type": "vectorSearch",
                "definition": {
                    "fields": [
                        {
                            "path": "embedding",
                            "numDimensions": 384,
                            "type": "vector",
                            "similarity": "cosine",
                        },
                        {"path": "user_id", "type": "filter"},
                        {"path": "is_compressed", "type": "filter"},
                    ],
                },
            }],
        })
        logger.info("vector_search_index_created")
    except Exception as e:
        # Index may already exist or Atlas Local not available
        logger.debug("vector_search_index_skipped", reason=str(e))


async def _ensure_kb_vector_search_index(db: AsyncIOMotorDatabase) -> None:
    """Create vector search index for kb_items collection."""
    try:
        await db.command({
            "createSearchIndexes": "kb_items",
            "indexes": [{
                "name": "kb_vector_index",
                "type": "vectorSearch",
                "definition": {
                    "fields": [
                        {
                            "path": "embedding",
                            "numDimensions": 384,
                            "type": "vector",
                            "similarity": "cosine",
                        },
                        {"path": "user_id", "type": "filter"},
                        {"path": "source_type", "type": "filter"},
                    ],
                },
            }],
        })
        logger.info("kb_vector_search_index_created")
    except Exception as e:
        logger.debug("kb_vector_search_index_skipped", reason=str(e))

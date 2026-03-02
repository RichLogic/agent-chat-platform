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
    logger.info("mongodb_indexes_created")

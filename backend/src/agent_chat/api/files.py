"""File upload endpoints."""

from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.config import get_settings
from agent_chat.db.repository import create_file, find_file_by_hash, get_file
from agent_chat.services.pdf_service import parse_pdf_to_chunks
from agent_chat.storage.pdf_store import save_pdf

router = APIRouter()

_ALLOWED_TYPES = {"application/pdf"}


@router.post("/api/files/upload")
async def upload_file(
    file: UploadFile,
    user_id: str = Depends(get_current_user_id),
):
    """Upload a PDF file. Returns file metadata."""
    settings = get_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    # Validate content type
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Read and check size
    file_bytes = await file.read()
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {settings.max_upload_size_mb}MB)",
        )

    # Validate PDF magic bytes
    if not file_bytes[:5].startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF file")

    # Content hash for deduplication
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Check if file already exists
    existing = await find_file_by_hash(content_hash)
    if existing:
        return {
            "id": existing["id"],
            "original_filename": file.filename or "unknown.pdf",
            "size_bytes": existing["size_bytes"],
            "page_count": existing.get("page_count"),
            "parse_status": existing["parse_status"],
            "is_duplicate": True,
        }

    # Save to disk
    storage_path = await save_pdf(settings.data_dir, content_hash, file_bytes)

    # Create DB record
    file_doc = await create_file(
        uploaded_by=user_id,
        content_hash=content_hash,
        original_filename=file.filename or "unknown.pdf",
        mime_type="application/pdf",
        size_bytes=len(file_bytes),
        storage_path=storage_path,
    )

    # Launch background parsing
    asyncio.create_task(
        parse_pdf_to_chunks(
            file_id=file_doc["id"],
            data_dir=settings.data_dir,
            storage_path=storage_path,
            content_hash=content_hash,
        )
    )

    return {
        "id": file_doc["id"],
        "original_filename": file_doc["original_filename"],
        "size_bytes": file_doc["size_bytes"],
        "page_count": None,
        "parse_status": "pending",
        "is_duplicate": False,
    }


@router.get("/api/files/{file_id}")
async def get_file_info(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get file metadata and parse status."""
    file_doc = await get_file(file_id)
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "id": file_doc["id"],
        "original_filename": file_doc["original_filename"],
        "size_bytes": file_doc["size_bytes"],
        "page_count": file_doc.get("page_count"),
        "parse_status": file_doc["parse_status"],
    }

"""File upload endpoints with streaming support."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.config import get_settings
from agent_chat.db.repository import create_file, find_file_by_hash, get_file
from agent_chat.services.pdf_service import parse_pdf_to_chunks
from agent_chat.storage.pdf_store import save_pdf_from_path

router = APIRouter()

_ALLOWED_TYPES = {"application/pdf"}
_CHUNK_SIZE = 64 * 1024  # 64KB read chunks


@router.post("/api/files/upload")
async def upload_file(
    file: UploadFile,
    user_id: str = Depends(get_current_user_id),
):
    """Upload a PDF file via streaming. Returns file metadata."""
    settings = get_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    # Validate content type
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Stream to a temporary file while hashing + validating
    tmp_dir = Path(settings.data_dir) / "uploads" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / uuid4().hex

    hasher = hashlib.sha256()
    total = 0
    validated_magic = False

    try:
        async with aiofiles.open(tmp_path, "wb") as f:
            while chunk := await file.read(_CHUNK_SIZE):
                if not validated_magic:
                    if not chunk[:5].startswith(b"%PDF-"):
                        raise HTTPException(status_code=400, detail="Invalid PDF file")
                    validated_magic = True
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large (max {settings.max_upload_size_mb}MB)",
                    )
                hasher.update(chunk)
                await f.write(chunk)

        if total == 0:
            raise HTTPException(status_code=400, detail="Empty file")

        content_hash = hasher.hexdigest()

        # Check dedup
        existing = await find_file_by_hash(content_hash)
        if existing:
            tmp_path.unlink(missing_ok=True)
            return {
                "id": existing["id"],
                "original_filename": file.filename or "unknown.pdf",
                "size_bytes": existing["size_bytes"],
                "page_count": existing.get("page_count"),
                "parse_status": existing["parse_status"],
                "is_duplicate": True,
            }

        # Move tmp file to final storage location
        storage_path = await save_pdf_from_path(settings.data_dir, content_hash, tmp_path)

        # Create DB record
        file_doc = await create_file(
            uploaded_by=user_id,
            content_hash=content_hash,
            original_filename=file.filename or "unknown.pdf",
            mime_type="application/pdf",
            size_bytes=total,
            storage_path=storage_path,
        )

        # Launch background parsing (with user_id and filename for KB ingestion)
        asyncio.create_task(
            parse_pdf_to_chunks(
                file_id=file_doc["id"],
                data_dir=settings.data_dir,
                storage_path=storage_path,
                content_hash=content_hash,
                user_id=user_id,
                filename=file.filename or "unknown.pdf",
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

    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


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

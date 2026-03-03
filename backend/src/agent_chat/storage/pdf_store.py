"""PDF file storage on disk."""

from __future__ import annotations

import shutil
from pathlib import Path

import aiofiles


async def save_pdf(data_dir: str, content_hash: str, file_bytes: bytes) -> str:
    """Save PDF bytes to disk. Returns relative storage path.

    Uses first 2 chars of hash as subdirectory to avoid too many files in one dir.
    """
    prefix = content_hash[:2]
    dir_path = Path(data_dir) / "uploads" / prefix
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{content_hash}.pdf"
    if not file_path.exists():
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_bytes)
    return f"uploads/{prefix}/{content_hash}.pdf"


async def save_pdf_from_path(data_dir: str, content_hash: str, src_path: Path) -> str:
    """Move a temporary PDF file to its final storage location. Returns relative storage path."""
    prefix = content_hash[:2]
    dir_path = Path(data_dir) / "uploads" / prefix
    dir_path.mkdir(parents=True, exist_ok=True)
    dest_path = dir_path / f"{content_hash}.pdf"
    if not dest_path.exists():
        shutil.move(str(src_path), str(dest_path))
    else:
        src_path.unlink(missing_ok=True)
    return f"uploads/{prefix}/{content_hash}.pdf"


def get_pdf_path(data_dir: str, storage_path: str) -> Path:
    """Resolve a relative storage path to an absolute path."""
    return Path(data_dir) / storage_path

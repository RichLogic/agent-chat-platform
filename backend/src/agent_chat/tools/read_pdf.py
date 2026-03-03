"""read_pdf tool — reads parsed PDF content from file_chunks."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog

from agent_chat.db.repository import get_file, get_file_chunks
from agent_chat.tools.base import Tool

logger = structlog.get_logger()


def _parse_pages_param(pages_str: str) -> list[int]:
    """Parse a pages string like '1-5' or '1,3,5' into a sorted list of ints."""
    result: set[int] = set()
    for part in pages_str.split(","):
        part = part.strip()
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            result.update(range(start, end + 1))
        elif part.isdigit():
            result.add(int(part))
    return sorted(result)


class ReadPdfTool(Tool):
    name = "read_pdf"
    description = "读取用户上传的 PDF 文件内容（Markdown格式）。可以读取全文或指定页码范围。"
    parameters = {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "文件ID（从用户消息的附件信息中获取）",
            },
            "pages": {
                "type": "string",
                "description": "页码范围，例如 '1-5' 或 '1,3,5'。不指定则读取全文。",
            },
        },
        "required": ["file_id"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        file_id = arguments.get("file_id", "")
        pages_str = arguments.get("pages", "")

        if not file_id:
            return {"error": "Missing file_id parameter"}

        # Get file metadata
        file_doc = await get_file(file_id)
        if not file_doc:
            return {"error": f"File not found: {file_id}"}

        content_hash = file_doc["content_hash"]

        # If parsing is still in progress, wait briefly then try
        if file_doc["parse_status"] in ("pending", "parsing"):
            for _ in range(5):
                await asyncio.sleep(1)
                file_doc = await get_file(file_id)
                if file_doc and file_doc["parse_status"] == "done":
                    break

        if file_doc["parse_status"] == "failed":
            return {"error": "PDF parsing failed for this file"}

        # Parse pages parameter
        page_numbers = _parse_pages_param(pages_str) if pages_str else None

        # Get chunks
        chunks = await get_file_chunks(content_hash, page_numbers=page_numbers)

        if not chunks:
            if file_doc["parse_status"] != "done":
                return {"error": "PDF is still being parsed, please try again shortly"}
            return {"error": "No content found in this PDF"}

        # Build response
        pages_content = []
        for chunk in chunks:
            pages_content.append({
                "page": chunk["page_number"],
                "content": chunk["content"],
            })

        return {
            "filename": file_doc["original_filename"],
            "total_pages": file_doc.get("page_count") or len(chunks),
            "pages_returned": len(pages_content),
            "pages": pages_content,
        }

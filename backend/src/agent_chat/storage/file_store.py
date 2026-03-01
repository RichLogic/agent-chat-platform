"""JSONL event file storage."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles


async def write_event(data_dir: str, run_id: str, event_dict: dict) -> None:
    """Append a JSON line to the events file for a run."""
    run_dir = Path(data_dir) / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    events_file = run_dir / "events.jsonl"
    line = json.dumps(event_dict, ensure_ascii=False, default=str) + "\n"
    async with aiofiles.open(events_file, "a") as f:
        await f.write(line)


async def read_events(data_dir: str, run_id: str) -> AsyncIterator[dict]:
    """Read events from a JSONL file as an async generator."""
    events_file = Path(data_dir) / "runs" / run_id / "events.jsonl"
    if not events_file.exists():
        return
    async with aiofiles.open(events_file, "r") as f:
        async for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

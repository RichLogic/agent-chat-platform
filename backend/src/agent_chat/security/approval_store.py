"""In-memory approval store for tool confirmation flow.

Pending approvals are held as asyncio.Event objects so the tool execution
coroutine can await a decision from the user.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class PendingApproval:
    __slots__ = (
        "id", "run_id", "tool_name", "arguments", "risk_level",
        "reason", "status", "created_at", "_event",
    )

    def __init__(
        self,
        *,
        run_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: str,
        reason: str,
    ) -> None:
        self.id = uuid.uuid4().hex
        self.run_id = run_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.risk_level = risk_level
        self.reason = reason
        self.status = ApprovalStatus.PENDING
        self.created_at = datetime.now(timezone.utc)
        self._event = asyncio.Event()

    async def wait(self, timeout: float = 120.0) -> ApprovalStatus:
        """Block until the user approves/denies or timeout expires."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self.status = ApprovalStatus.EXPIRED
        return self.status

    def resolve(self, approved: bool) -> None:
        self.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        self._event.set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }


class ApprovalStore:
    """Thread-safe in-memory store for pending approvals."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingApproval] = {}

    def create(
        self,
        *,
        run_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: str,
        reason: str,
    ) -> PendingApproval:
        approval = PendingApproval(
            run_id=run_id,
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk_level,
            reason=reason,
        )
        self._pending[approval.id] = approval
        return approval

    def get(self, approval_id: str) -> PendingApproval | None:
        return self._pending.get(approval_id)

    def resolve(self, approval_id: str, approved: bool) -> PendingApproval | None:
        approval = self._pending.get(approval_id)
        if approval and approval.status == ApprovalStatus.PENDING:
            approval.resolve(approved)
            return approval
        return None

    def list_pending(self, run_id: str | None = None) -> list[dict[str, Any]]:
        items = self._pending.values()
        if run_id:
            items = [a for a in items if a.run_id == run_id]
        return [
            a.to_dict() for a in items
            if a.status == ApprovalStatus.PENDING
        ]

    def cleanup(self, run_id: str) -> None:
        """Remove all approvals for a completed run."""
        to_delete = [k for k, v in self._pending.items() if v.run_id == run_id]
        for k in to_delete:
            del self._pending[k]


# Module-level singleton
_store: ApprovalStore | None = None


def get_approval_store() -> ApprovalStore:
    global _store
    if _store is None:
        _store = ApprovalStore()
    return _store

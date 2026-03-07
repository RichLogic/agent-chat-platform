"""Approval API — approve or deny pending tool confirmations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent_chat.auth.middleware import get_current_user_id
from agent_chat.security.approval_store import get_approval_store

router = APIRouter()


class ApprovalAction(BaseModel):
    approved: bool


@router.get("/api/approvals")
async def list_pending_approvals(
    run_id: str | None = None,
    _user_id: str = Depends(get_current_user_id),
):
    """List pending approvals, optionally filtered by run_id."""
    store = get_approval_store()
    return {"items": store.list_pending(run_id=run_id)}


@router.post("/api/approvals/{approval_id}")
async def resolve_approval(
    approval_id: str,
    body: ApprovalAction,
    _user_id: str = Depends(get_current_user_id),
):
    """Approve or deny a pending tool call."""
    store = get_approval_store()
    approval = store.resolve(approval_id, body.approved)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found or already resolved")
    return {"status": approval.status.value, "approval_id": approval_id}

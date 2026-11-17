"""Approval service (spec §12.3; docs/SECURITY.md §8). The only gate in front of external actions."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApprovalExpired, ApprovalMismatch, ApprovalRequired, NotFound
from app.domain.text import sha256_hex
from app.models import Approval
from app.services.common import audit


def payload_hash(payload: dict[str, Any]) -> str:
    return "sha256:" + sha256_hex(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


async def create_pending(s: AsyncSession, user_id: uuid.UUID, action_type: str, reference_type: str, reference_id: uuid.UUID,
                         payload: dict[str, Any], preview: dict[str, Any] | None = None, agent_run_id: uuid.UUID | None = None,
                         ttl_hours: int = 24) -> Approval:
    await s.execute(update(Approval).where(Approval.user_id == user_id, Approval.reference_type == reference_type,
                                           Approval.reference_id == reference_id, Approval.action_type == action_type,
                                           Approval.status.in_(("pending", "approved"))).values(status="expired"))
    now = datetime.now(tz=UTC)
    approval = Approval(user_id=user_id, action_type=action_type, reference_type=reference_type, reference_id=reference_id,
                        payload_hash=payload_hash(payload), payload_preview=preview or payload, status="pending",
                        agent_run_id=agent_run_id, requested_at=now, expires_at=now + timedelta(hours=ttl_hours))
    s.add(approval)
    await s.flush()
    await audit(s, user_id, "approval.requested", reference_type, reference_id, action_type=action_type, approval_id=str(approval.id))
    return approval


async def decide(s: AsyncSession, user_id: uuid.UUID, approval_id: uuid.UUID, given_hash: str, approve: bool = True) -> Approval:
    approval = (await s.execute(select(Approval).where(Approval.id == approval_id, Approval.user_id == user_id)
                                .with_for_update())).scalar_one_or_none()
    if approval is None:
        raise NotFound()
    if approval.status in ("executed", "approved") and approve:
        if approval.payload_hash != given_hash:
            raise ApprovalMismatch()
        return approval  # idempotent replay
    if approval.status != "pending":
        raise ApprovalRequired(f"This approval is {approval.status}.", details={"status": approval.status})
    if approval.expires_at < datetime.now(tz=UTC):
        approval.status = "expired"
        raise ApprovalExpired()
    if approval.payload_hash != given_hash:
        raise ApprovalMismatch()
    approval.status = "approved" if approve else "rejected"
    approval.decided_at = datetime.now(tz=UTC)
    await audit(s, user_id, "approval.decided", approval.reference_type, approval.reference_id,
                decision=approval.status, approval_id=str(approval.id))
    return approval


async def consume(s: AsyncSession, user_id: uuid.UUID, approval_id: uuid.UUID, current_payload: dict[str, Any]) -> Approval:
    """Atomically mark an approved, unexpired, hash-matching approval as executed. Raises if anything differs."""
    h = payload_hash(current_payload)
    row = (await s.execute(text(
        "UPDATE approvals SET status = 'executed', executed_at = now() WHERE id = :id AND user_id = :uid "
        "AND status = 'approved' AND payload_hash = :h AND expires_at > now() RETURNING id"),
        {"id": approval_id, "uid": user_id, "h": h})).first()
    if row is None:
        existing = await s.get(Approval, approval_id)
        if existing is None or existing.user_id != user_id:
            raise NotFound()
        if existing.payload_hash != h:
            raise ApprovalMismatch("The item changed after approval. Request approval again.")
        if existing.expires_at < datetime.now(tz=UTC):
            raise ApprovalExpired()
        raise ApprovalRequired(f"Approval is {existing.status}.", details={"status": existing.status})
    approval = await s.get(Approval, approval_id)
    await s.refresh(approval)
    return approval


async def record_result(s: AsyncSession, approval: Approval, ok: bool, result: dict[str, Any],
                        external: dict[str, Any] | None = None) -> None:
    approval.execution_result = result
    approval.external_confirmation = external
    if not ok:
        approval.status = "failed"
    await audit(s, approval.user_id, "approval.executed", approval.reference_type, approval.reference_id,
                ok=ok, approval_id=str(approval.id))

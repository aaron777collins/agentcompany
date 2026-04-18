"""Approvals API — /api/v1/approvals.

Human-in-the-loop approval gates.  Agents propose actions; humans approve or
deny them here before the agent proceeds.  The frontend polls this endpoint to
surface pending items on the approvals dashboard.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.dependencies import DBSession, OrgMember, Pagination
from app.models.approval import Approval
from app.schemas.approval import ApprovalDecision, ApprovalRead
from app.schemas.common import DataResponse, make_list_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/",
    summary="List approvals",
)
async def list_approvals(
    db: DBSession,
    claims: OrgMember,
    pagination: Pagination,
    company_id: str | None = Query(default=None),
    approval_status: str | None = Query(default=None, alias="status"),
    agent_id: str | None = Query(default=None),
) -> dict:
    """Return approvals visible to the caller's org, newest first.

    Defaults to showing all statuses.  Pass ?status=pending to filter to
    items awaiting a decision (the most common use case).
    """
    query = select(Approval).where(
        Approval.org_id == claims.org_id,
        Approval.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Approval.company_id == company_id)
    if approval_status:
        query = query.where(Approval.status == approval_status)
    if agent_id:
        query = query.where(Approval.agent_id == agent_id)

    total: int = await db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0
    rows = await db.scalars(
        query.order_by(Approval.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    items = [ApprovalRead.model_validate(a) for a in rows]
    return make_list_response(items, total, pagination.limit, pagination.offset)


@router.post(
    "/{approval_id}/approve",
    response_model=DataResponse[ApprovalRead],
    status_code=status.HTTP_200_OK,
    summary="Approve a pending action",
)
async def approve(
    approval_id: str,
    body: ApprovalDecision,
    db: DBSession,
    claims: OrgMember,
) -> DataResponse[ApprovalRead]:
    """Mark a pending approval as approved.

    Only pending approvals may be approved — attempting to re-decide an
    already-decided approval returns 409 Conflict.
    """
    approval = await _get_or_404(db, approval_id, claims.org_id)
    _require_pending(approval)

    approval.status = "approved"
    approval.decided_by = claims.sub
    approval.decided_at = datetime.now(timezone.utc)
    approval.decision_note = body.note

    await db.flush()
    await db.refresh(approval)

    logger.info("Approval %s approved by %s", approval_id, claims.sub)
    return DataResponse(data=ApprovalRead.model_validate(approval))


@router.post(
    "/{approval_id}/deny",
    response_model=DataResponse[ApprovalRead],
    status_code=status.HTTP_200_OK,
    summary="Deny a pending action",
)
async def deny(
    approval_id: str,
    body: ApprovalDecision,
    db: DBSession,
    claims: OrgMember,
) -> DataResponse[ApprovalRead]:
    """Mark a pending approval as denied.

    Only pending approvals may be denied — attempting to re-decide an
    already-decided approval returns 409 Conflict.
    """
    approval = await _get_or_404(db, approval_id, claims.org_id)
    _require_pending(approval)

    approval.status = "denied"
    approval.decided_by = claims.sub
    approval.decided_at = datetime.now(timezone.utc)
    approval.decision_note = body.note

    await db.flush()
    await db.refresh(approval)

    logger.info("Approval %s denied by %s", approval_id, claims.sub)
    return DataResponse(data=ApprovalRead.model_validate(approval))


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(db: DBSession, approval_id: str, org_id: str) -> Approval:
    approval = await db.scalar(
        select(Approval).where(
            Approval.id == approval_id,
            Approval.org_id == org_id,
            Approval.deleted_at.is_(None),
        )
    )
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_id}' not found",
        )
    return approval


def _require_pending(approval: Approval) -> None:
    """Raise 409 if the approval has already been decided."""
    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Approval '{approval.id}' has already been decided "
                f"(status: {approval.status})"
            ),
        )

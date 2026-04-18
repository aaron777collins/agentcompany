"""Tasks API — /api/v1/tasks."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.dependencies import DBSession, OrgAdmin, OrgMember, Pagination
from app.models.task import Task
from app.schemas.common import DataResponse, make_list_response
from app.schemas.task import TaskAssign, TaskCreate, TaskRead, TaskUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/",
    response_model=DataResponse[TaskRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
)
async def create_task(
    body: TaskCreate,
    db: DBSession,
    claims: OrgMember,
) -> DataResponse[TaskRead]:
    task = Task(
        org_id=claims.org_id,
        company_id=body.company_id,
        title=body.title,
        description=body.description,
        assigned_to=body.assigned_to,
        assigned_type=body.assigned_type,
        priority=body.priority,
        due_at=body.due_at,
        tags=body.tags,
        parent_task_id=body.parent_task_id,
        metadata_=body.metadata,
        created_by=claims.sub,
        status="backlog",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    logger.info("Task created: %s (company=%s)", task.id, body.company_id)
    return DataResponse(data=TaskRead.model_validate(task))


@router.get("/", summary="List tasks")
async def list_tasks(
    db: DBSession,
    claims: OrgMember,
    pagination: Pagination,
    company_id: str | None = Query(default=None),
    task_status: str | None = Query(default=None, alias="status"),
    assigned_to: str | None = Query(default=None),
    priority: str | None = Query(default=None),
) -> dict:
    query = select(Task).where(
        Task.org_id == claims.org_id,
        Task.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Task.company_id == company_id)
    if task_status:
        query = query.where(Task.status == task_status)
    if assigned_to:
        query = query.where(Task.assigned_to == assigned_to)
    if priority:
        query = query.where(Task.priority == priority)

    total: int = await db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0
    rows = await db.scalars(
        query.order_by(Task.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    items = [TaskRead.model_validate(t) for t in rows]
    return make_list_response(items, total, pagination.limit, pagination.offset)


@router.get(
    "/{task_id}",
    response_model=DataResponse[TaskRead],
    summary="Get a task",
)
async def get_task(
    task_id: str,
    db: DBSession,
    claims: OrgMember,
) -> DataResponse[TaskRead]:
    task = await _get_or_404(db, task_id, claims.org_id)
    return DataResponse(data=TaskRead.model_validate(task))


@router.put(
    "/{task_id}",
    response_model=DataResponse[TaskRead],
    summary="Update a task",
)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    db: DBSession,
    claims: OrgMember,
) -> DataResponse[TaskRead]:
    task = await _get_or_404(db, task_id, claims.org_id)

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.status is not None:
        _apply_status_transition(task, body.status)
    if body.priority is not None:
        task.priority = body.priority
    if body.assigned_to is not None:
        task.assigned_to = body.assigned_to
        task.assigned_type = body.assigned_type
    if body.due_at is not None:
        task.due_at = body.due_at
    if body.tags is not None:
        task.tags = body.tags
    if body.metadata is not None:
        task.metadata_ = {**task.metadata_, **body.metadata}

    task.version += 1
    await db.flush()
    await db.refresh(task)
    return DataResponse(data=TaskRead.model_validate(task))


@router.post(
    "/{task_id}/assign",
    response_model=DataResponse[TaskRead],
    summary="Assign a task to an agent or user",
)
async def assign_task(
    task_id: str,
    body: TaskAssign,
    db: DBSession,
    claims: OrgMember,
) -> DataResponse[TaskRead]:
    task = await _get_or_404(db, task_id, claims.org_id)
    task.assigned_to = body.assignee_id
    task.assigned_type = body.assignee_type
    task.version += 1
    await db.flush()
    await db.refresh(task)
    return DataResponse(data=TaskRead.model_validate(task))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_status_transition(task: Task, new_status: str) -> None:
    """Apply a status change and update derived timestamps."""
    task.status = new_status
    now = datetime.now(timezone.utc)
    if new_status == "in_progress" and task.started_at is None:
        task.started_at = now
    elif new_status in ("done", "cancelled"):
        task.completed_at = now


async def _get_or_404(db: DBSession, task_id: str, org_id: str) -> Task:
    task = await db.scalar(
        select(Task).where(
            Task.id == task_id,
            Task.org_id == org_id,
            Task.deleted_at.is_(None),
        )
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    return task

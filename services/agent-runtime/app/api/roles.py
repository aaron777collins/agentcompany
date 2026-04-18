"""Roles API — /api/v1/roles."""

import logging

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.dependencies import DBSession, OrgAdmin, OrgMember, Pagination
from app.models.role import Role
from app.schemas.common import DataResponse, make_list_response
from app.schemas.role import RoleCreate, RoleRead, RoleUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/",
    response_model=DataResponse[RoleRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a role",
)
async def create_role(
    body: RoleCreate,
    db: DBSession,
    claims: OrgAdmin,
) -> DataResponse[RoleRead]:
    existing = await db.scalar(
        select(Role).where(
            Role.company_id == body.company_id,
            Role.slug == body.slug,
            Role.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role '{body.slug}' already exists in company '{body.company_id}'",
        )

    # Validate that parent role exists if provided
    if body.reports_to_role_id:
        parent = await db.scalar(
            select(Role).where(
                Role.id == body.reports_to_role_id,
                Role.deleted_at.is_(None),
            )
        )
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"reports_to_role_id '{body.reports_to_role_id}' does not exist",
            )

    role = Role(
        org_id=claims.org_id,
        company_id=body.company_id,
        name=body.name,
        slug=body.slug,
        description=body.description,
        level=body.level,
        reports_to_role_id=body.reports_to_role_id,
        permissions=body.permissions,
        tool_access=body.tool_access,
        max_headcount=body.max_headcount,
        headcount_type=body.headcount_type,
    )
    db.add(role)
    await db.flush()
    await db.refresh(role)

    logger.info("Role created: %s (company=%s)", role.id, body.company_id)
    return DataResponse(data=RoleRead.model_validate(role))


@router.get("/", summary="List roles")
async def list_roles(
    db: DBSession,
    claims: OrgMember,
    pagination: Pagination,
    company_id: str | None = Query(default=None),
) -> dict:
    query = select(Role).where(
        Role.org_id == claims.org_id,
        Role.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Role.company_id == company_id)

    total: int = await db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0
    rows = await db.scalars(
        query.order_by(Role.level.asc(), Role.name.asc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    items = [RoleRead.model_validate(r) for r in rows]
    return make_list_response(items, total, pagination.limit, pagination.offset)


@router.get(
    "/{role_id}",
    response_model=DataResponse[RoleRead],
    summary="Get a role",
)
async def get_role(
    role_id: str,
    db: DBSession,
    claims: OrgMember,
) -> DataResponse[RoleRead]:
    role = await _get_or_404(db, role_id, claims.org_id)
    return DataResponse(data=RoleRead.model_validate(role))


@router.put(
    "/{role_id}",
    response_model=DataResponse[RoleRead],
    summary="Update a role",
)
async def update_role(
    role_id: str,
    body: RoleUpdate,
    db: DBSession,
    claims: OrgAdmin,
) -> DataResponse[RoleRead]:
    role = await _get_or_404(db, role_id, claims.org_id)

    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.level is not None:
        role.level = body.level
    if body.reports_to_role_id is not None:
        role.reports_to_role_id = body.reports_to_role_id
    if body.permissions is not None:
        role.permissions = body.permissions
    if body.tool_access is not None:
        role.tool_access = body.tool_access
    if body.max_headcount is not None:
        role.max_headcount = body.max_headcount
    if body.headcount_type is not None:
        role.headcount_type = body.headcount_type

    await db.flush()
    await db.refresh(role)
    return DataResponse(data=RoleRead.model_validate(role))


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a role",
)
async def delete_role(
    role_id: str,
    db: DBSession,
    claims: OrgAdmin,
) -> None:
    role = await _get_or_404(db, role_id, claims.org_id)
    role.soft_delete()
    logger.info("Role soft-deleted: %s", role_id)


async def _get_or_404(db: DBSession, role_id: str, org_id: str) -> Role:
    role = await db.scalar(
        select(Role).where(
            Role.id == role_id,
            Role.org_id == org_id,
            Role.deleted_at.is_(None),
        )
    )
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_id}' not found",
        )
    return role

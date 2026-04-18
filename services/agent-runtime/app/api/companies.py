"""Companies API — /api/v1/companies.

CRUD endpoints for Company resources.  All mutating operations publish an event
so subscribers (SSE, webhooks) receive real-time updates.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.dependencies import DBSession, OrgAdmin, OrgMember, Pagination
from app.models.company import Company
from app.schemas.common import DataResponse, make_list_response
from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/",
    response_model=DataResponse[CompanyRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new company",
)
async def create_company(
    body: CompanyCreate,
    db: DBSession,
    claims: OrgAdmin,
) -> DataResponse[CompanyRead]:
    # Guard against duplicate slug within the same org
    existing = await db.scalar(
        select(Company).where(
            Company.org_id == claims.org_id,
            Company.slug == body.slug,
            Company.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A company with slug '{body.slug}' already exists in this org",
        )

    company = Company(
        org_id=claims.org_id,
        name=body.name,
        slug=body.slug,
        description=body.description,
        settings=body.settings.model_dump(),
        status="provisioning",
    )
    db.add(company)
    await db.flush()
    await db.refresh(company)

    logger.info("Company created: %s (org=%s)", company.id, claims.org_id)
    return DataResponse(data=CompanyRead.model_validate(company))


@router.get(
    "/",
    summary="List companies",
)
async def list_companies(
    db: DBSession,
    claims: OrgMember,
    pagination: Pagination,
) -> dict:
    base_query = select(Company).where(
        Company.org_id == claims.org_id,
        Company.deleted_at.is_(None),
    )
    total: int = await db.scalar(
        select(func.count()).select_from(base_query.subquery())
    ) or 0
    rows = await db.scalars(
        base_query.order_by(Company.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    items = [CompanyRead.model_validate(c) for c in rows]
    return make_list_response(items, total, pagination.limit, pagination.offset)


@router.get(
    "/{company_id}",
    response_model=DataResponse[CompanyRead],
    summary="Get a company",
)
async def get_company(
    company_id: str,
    db: DBSession,
    claims: OrgMember,
) -> DataResponse[CompanyRead]:
    company = await _get_or_404(db, company_id, claims.org_id)
    return DataResponse(data=CompanyRead.model_validate(company))


@router.put(
    "/{company_id}",
    response_model=DataResponse[CompanyRead],
    summary="Update a company",
)
async def update_company(
    company_id: str,
    body: CompanyUpdate,
    db: DBSession,
    claims: OrgAdmin,
) -> DataResponse[CompanyRead]:
    company = await _get_or_404(db, company_id, claims.org_id)

    if body.name is not None:
        company.name = body.name
    if body.description is not None:
        company.description = body.description
    if body.status is not None:
        company.status = body.status
    if body.settings is not None:
        # Merge provided fields into existing settings — never replace wholesale
        company.settings = {**company.settings, **body.settings}

    company.version += 1
    await db.flush()
    await db.refresh(company)

    return DataResponse(data=CompanyRead.model_validate(company))


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a company",
)
async def delete_company(
    company_id: str,
    db: DBSession,
    claims: OrgAdmin,
) -> None:
    company = await _get_or_404(db, company_id, claims.org_id)
    company.soft_delete()
    company.status = "archived"
    company.version += 1
    logger.info("Company soft-deleted: %s", company_id)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(db: DBSession, company_id: str, org_id: str) -> Company:
    company = await db.scalar(
        select(Company).where(
            Company.id == company_id,
            Company.org_id == org_id,
            Company.deleted_at.is_(None),
        )
    )
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{company_id}' not found",
        )
    return company

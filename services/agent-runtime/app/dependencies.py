"""FastAPI dependency injection.

This module centralises all Depends() callables so routes stay clean.  Every
dependency is a function that FastAPI calls per-request (or per-lifespan for
cached ones like get_settings).
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.events import EventBus, get_event_bus
from app.core.security import AuthError, TokenClaims, validate_token


# ── Database ──────────────────────────────────────────────────────────────────

DBSession = Annotated[AsyncSession, Depends(get_db)]


# ── Authentication ────────────────────────────────────────────────────────────

async def _get_token_claims(
    authorization: Annotated[str | None, Header()] = None,
) -> TokenClaims:
    """Extract and validate the Bearer JWT from the Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return await validate_token(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUser = Annotated[TokenClaims, Depends(_get_token_claims)]


def require_org_member(claims: CurrentUser) -> TokenClaims:
    """Require the caller to have at least org:member role."""
    allowed = {"org:member", "org:admin", "company:admin", "company:member", "agent"}
    if not (set(claims.roles) & allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: org membership required",
        )
    return claims


def require_org_admin(claims: CurrentUser) -> TokenClaims:
    """Require the caller to have org:admin role."""
    if "org:admin" not in claims.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: org admin required",
        )
    return claims


OrgMember = Annotated[TokenClaims, Depends(require_org_member)]
OrgAdmin = Annotated[TokenClaims, Depends(require_org_admin)]


# ── Event bus ─────────────────────────────────────────────────────────────────

def _get_bus(request: Request) -> EventBus:
    """Read the EventBus off app state — placed there during lifespan startup."""
    bus: EventBus | None = getattr(request.app.state, "event_bus", None)
    if bus is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event bus is not available",
        )
    return bus


Bus = Annotated[EventBus, Depends(_get_bus)]


# ── Pagination ────────────────────────────────────────────────────────────────

class PaginationParams:
    def __init__(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> None:
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="limit must be between 1 and 100",
            )
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="offset must be non-negative",
            )
        self.limit = limit
        self.offset = offset


Pagination = Annotated[PaginationParams, Depends(PaginationParams)]

"""FastAPI dependency injection.

This module centralises all Depends() callables so routes stay clean.  Every
dependency is a function that FastAPI calls per-request (or per-lifespan for
cached ones like get_settings).
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.core.events import EventBus
from app.core.security import AuthError, TokenClaims, validate_token
from app.engine.engine_service import AgentEngineService

# ── Database ──────────────────────────────────────────────────────────────────


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession and set the RLS context for the current company.

    Row-Level Security policies on agents, tasks, and events use
    ``current_setting('app.current_company_id')`` to filter rows.  Without
    this SET LOCAL the RLS policies return empty result sets for every query.

    SET LOCAL scopes the GUC to the current transaction only, so parallel
    requests on different connections never bleed into each other.
    """
    factory = get_session_factory()
    async with factory() as session:
        # Attach the company_id GUC if the request carries verified JWT claims.
        # The auth middleware (if any) may store claims on request.state; the
        # per-endpoint dependency (_get_token_claims) also stores them there.
        claims: TokenClaims | None = getattr(request.state, "token_claims", None)
        if claims is not None and claims.company_id:
            # Parameterized to prevent injection — never use an f-string here.
            await session.execute(
                text("SET LOCAL app.current_company_id = :cid"),
                {"cid": claims.company_id},
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DBSession = Annotated[AsyncSession, Depends(get_db)]


# ── Authentication ────────────────────────────────────────────────────────────


async def _get_token_claims(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenClaims:
    """
    Extract and validate the Bearer JWT from the Authorization header.

    Stores the validated claims on request.state.token_claims so that the
    get_db dependency can read the company_id for RLS context-setting without
    creating a hard dependency between the two Depends() callables.
    """
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
        claims = await validate_token(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Store on request.state so get_db can set the RLS company GUC without
    # being listed as a dependency of every endpoint that uses DBSession.
    request.state.token_claims = claims
    return claims


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


# ── Agent engine ─────────────────────────────────────────────────────────────


def _get_agent_manager(request: Request) -> AgentEngineService:
    """Return the AgentEngineService placed on app.state during lifespan startup."""
    manager: AgentEngineService | None = getattr(request.app.state, "agent_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent engine is not available",
        )
    return manager


EngineService = Annotated[AgentEngineService, Depends(_get_agent_manager)]


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

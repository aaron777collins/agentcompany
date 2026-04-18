"""JWT validation against Keycloak-issued tokens.

Tokens are validated by:
1. Fetching the JWKS from Keycloak at startup (cached; refreshed every hour).
2. Verifying the signature, expiry, issuer, and audience on every request.
3. Returning a parsed Claims object for downstream authorization checks.

We deliberately do NOT contact Keycloak on the hot path — only the cached
public key set is used.  This means revoked tokens stay valid until they
expire (Keycloak's default is 1-hour access tokens).
"""

import logging
import time
from dataclasses import dataclass, field

import httpx
from jose import JWTError, jwt
from jose.backends import RSAKey

from app.config import get_settings

logger = logging.getLogger(__name__)

_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS = 3600  # refresh public keys at most once per hour


@dataclass
class TokenClaims:
    sub: str
    org_id: str
    is_agent: bool
    agent_id: str | None
    company_id: str | None
    roles: list[str] = field(default_factory=list)
    email: str | None = None
    name: str | None = None


class AuthError(Exception):
    """Raised when a token is invalid, expired, or missing required claims."""


async def _fetch_jwks() -> dict:
    """Download Keycloak's public key set.  Called at most every TTL seconds."""
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL_SECONDS:
        return _jwks_cache

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(settings.jwks_uri)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_fetched_at = now
            logger.info("JWKS refreshed from %s", settings.jwks_uri)
    except Exception as exc:
        if _jwks_cache:
            # Use stale cache rather than fail hard — Keycloak may be restarting
            logger.warning("Failed to refresh JWKS, using stale cache: %s", exc)
        else:
            raise AuthError(f"Unable to fetch JWKS from Keycloak: {exc}") from exc

    return _jwks_cache


async def validate_token(raw_token: str) -> TokenClaims:
    """Validate a Bearer JWT and return its claims.

    Raises AuthError for any validation failure so callers can translate to 401.
    """
    settings = get_settings()
    jwks = await _fetch_jwks()

    try:
        claims = jwt.decode(
            raw_token,
            jwks,
            algorithms=["RS256"],
            audience="agentcompany-api",
            issuer=settings.token_issuer,
            options={"verify_exp": True},
        )
    except JWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc

    sub = claims.get("sub")
    if not sub:
        raise AuthError("Token missing 'sub' claim")

    org_id = claims.get("org_id")
    if not org_id:
        raise AuthError("Token missing 'org_id' claim")

    realm_roles: list[str] = (
        claims.get("realm_access", {}).get("roles", [])
    )

    return TokenClaims(
        sub=sub,
        org_id=org_id,
        is_agent=bool(claims.get("agent", False)),
        agent_id=claims.get("agent_id"),
        company_id=claims.get("company_id"),
        roles=realm_roles,
        email=claims.get("email"),
        name=claims.get("name"),
    )

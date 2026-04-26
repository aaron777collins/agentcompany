"""
Tests for JWT authentication middleware.

These tests exercise app.core.security.validate_token directly (unit level)
and verify that the FastAPI dependency layer correctly translates auth
failures to 401 responses.

Keycloak is never called — tests use a local RSA key pair to generate
realistic JWTs and a mocked JWKS endpoint.
"""

from __future__ import annotations

import base64
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from jose import jwt as jose_jwt

from app.core.security import AuthError, TokenClaims, _fetch_jwks, validate_token


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# RSA key pair for signing test tokens
# ---------------------------------------------------------------------------

_PRIVATE_KEY = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend(),
)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


def _int_to_base64url(n: int) -> str:
    """Encode an integer as base64url (big-endian, no padding)."""
    length = (n.bit_length() + 7) // 8
    raw = n.to_bytes(length, byteorder="big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


# Build a minimal JWKS containing the test public key in correct JWK format.
_KID = "test-key-1"
_pub_numbers = _PUBLIC_KEY.public_numbers()
_JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "use": "sig",
            "kid": _KID,
            "alg": "RS256",
            "n": _int_to_base64url(_pub_numbers.n),
            "e": _int_to_base64url(_pub_numbers.e),
        }
    ]
}

# The token issuer value must match what get_settings() returns.
# Use patch to override it in the tests.
_TEST_ISSUER = "http://keycloak:8080/auth/realms/agentcompany"


def _make_token(
    sub: str = "user-001",
    org_id: str = "org-001",
    iss: str = _TEST_ISSUER,
    aud: str = "agentcompany-api",
    exp_offset: int = 3600,
    extra_claims: dict | None = None,
) -> str:
    """Generate a signed RS256 JWT using the test private key."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "org_id": org_id,
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + exp_offset,
        "realm_access": {"roles": ["org:member"]},
    }
    if extra_claims:
        payload.update(extra_claims)

    return jose_jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256", headers={"kid": _KID})


def _patch_validate(mock_jwks):
    """Return the combined patch context for validate_token tests."""
    mock_jwks.return_value = _JWKS
    return mock_jwks


# ---------------------------------------------------------------------------
# Unit tests for validate_token
# ---------------------------------------------------------------------------


async def test_valid_jwt_accepted():
    """A well-formed, signed, non-expired token returns TokenClaims."""
    token = _make_token()

    with patch("app.core.security._fetch_jwks", new_callable=AsyncMock) as mock_jwks, \
         patch("app.core.security.get_settings") as mock_settings:
        mock_jwks.return_value = _JWKS
        mock_settings.return_value.token_issuer = _TEST_ISSUER
        claims = await validate_token(token)

    assert isinstance(claims, TokenClaims)
    assert claims.sub == "user-001"
    assert claims.org_id == "org-001"


async def test_expired_jwt_rejected():
    """A token with exp in the past must raise AuthError."""
    token = _make_token(exp_offset=-1)  # already expired

    with patch("app.core.security._fetch_jwks", new_callable=AsyncMock) as mock_jwks, \
         patch("app.core.security.get_settings") as mock_settings:
        mock_jwks.return_value = _JWKS
        mock_settings.return_value.token_issuer = _TEST_ISSUER
        with pytest.raises(AuthError, match="Invalid token"):
            await validate_token(token)


async def test_invalid_signature_rejected():
    """A token signed with a different key must raise AuthError."""
    other_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    payload = {
        "sub": "user-001",
        "org_id": "org-001",
        "iss": _TEST_ISSUER,
        "aud": "agentcompany-api",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "realm_access": {"roles": []},
    }
    bad_token = jose_jwt.encode(payload, other_key, algorithm="RS256")

    with patch("app.core.security._fetch_jwks", new_callable=AsyncMock) as mock_jwks, \
         patch("app.core.security.get_settings") as mock_settings:
        mock_jwks.return_value = _JWKS  # JWKS contains a DIFFERENT public key
        mock_settings.return_value.token_issuer = _TEST_ISSUER
        with pytest.raises(AuthError):
            await validate_token(bad_token)


async def test_missing_sub_rejected():
    """A token without the 'sub' claim must raise AuthError."""
    now = int(time.time())
    payload = {
        "org_id": "org-001",
        "iss": _TEST_ISSUER,
        "aud": "agentcompany-api",
        "iat": now,
        "exp": now + 3600,
        "realm_access": {"roles": []},
    }
    no_sub_token = jose_jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256")

    with patch("app.core.security._fetch_jwks", new_callable=AsyncMock) as mock_jwks, \
         patch("app.core.security.get_settings") as mock_settings:
        mock_jwks.return_value = _JWKS
        mock_settings.return_value.token_issuer = _TEST_ISSUER
        with pytest.raises(AuthError, match="sub"):
            await validate_token(no_sub_token)


async def test_missing_org_id_rejected():
    """A token without the 'org_id' claim must raise AuthError."""
    now = int(time.time())
    payload = {
        "sub": "user-001",
        "iss": _TEST_ISSUER,
        "aud": "agentcompany-api",
        "iat": now,
        "exp": now + 3600,
        "realm_access": {"roles": []},
    }
    token = jose_jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256")

    with patch("app.core.security._fetch_jwks", new_callable=AsyncMock) as mock_jwks, \
         patch("app.core.security.get_settings") as mock_settings:
        mock_jwks.return_value = _JWKS
        mock_settings.return_value.token_issuer = _TEST_ISSUER
        with pytest.raises(AuthError, match="org_id"):
            await validate_token(token)


async def test_token_claims_populated_correctly():
    """TokenClaims fields are mapped correctly from JWT payload."""
    token = _make_token(
        sub="agent-123",
        extra_claims={
            "agent": True,
            "agent_id": "agent-123",
            "company_id": "cmp_abc",
            "email": "agent@co.example",
            "name": "Sales Agent",
            "realm_access": {"roles": ["org:admin", "agent"]},
        },
    )

    with patch("app.core.security._fetch_jwks", new_callable=AsyncMock) as mock_jwks, \
         patch("app.core.security.get_settings") as mock_settings:
        mock_jwks.return_value = _JWKS
        mock_settings.return_value.token_issuer = _TEST_ISSUER
        claims = await validate_token(token)

    assert claims.is_agent is True
    assert claims.agent_id == "agent-123"
    assert claims.company_id == "cmp_abc"
    assert "org:admin" in claims.roles


# ---------------------------------------------------------------------------
# Integration: dependency layer returns 401 for missing/invalid auth header
# ---------------------------------------------------------------------------


def _build_raw_app_with_db():
    """
    Build a create_app() instance where ONLY the DB dependency is overridden
    so the session factory is reachable, but auth is NOT overridden.
    This lets us test that missing/bad tokens produce 401.
    """
    from app.main import create_app
    from app.dependencies import get_db
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    _engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    _factory = async_sessionmaker(bind=_engine, expire_on_commit=False)

    raw_app = create_app()

    async def _fake_db():
        async with _factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    raw_app.dependency_overrides[get_db] = _fake_db
    return raw_app


async def test_missing_auth_header_returns_401():
    """Endpoint requests without an Authorization header return 401."""
    from httpx import ASGITransport, AsyncClient

    raw_app = _build_raw_app_with_db()
    transport = ASGITransport(app=raw_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/api/v1/companies/")
    assert resp.status_code == 401


async def test_malformed_auth_header_returns_401():
    """Authorization header not in 'Bearer <token>' format returns 401."""
    from httpx import ASGITransport, AsyncClient

    raw_app = _build_raw_app_with_db()
    transport = ASGITransport(app=raw_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get(
            "/api/v1/companies/",
            headers={"Authorization": "Token not-a-bearer"},
        )
    assert resp.status_code == 401


async def test_invalid_jwt_returns_401():
    """A JWT with a bad signature returns 401 (not 500)."""
    from httpx import ASGITransport, AsyncClient

    raw_app = _build_raw_app_with_db()
    transport = ASGITransport(app=raw_app)

    garbage_token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.invalidsig"

    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        with patch("app.core.security._fetch_jwks", new_callable=AsyncMock) as mock_jwks:
            mock_jwks.return_value = _JWKS
            resp = await ac.get(
                "/api/v1/companies/",
                headers={"Authorization": f"Bearer {garbage_token}"},
            )
    assert resp.status_code == 401

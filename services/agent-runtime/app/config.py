"""Application configuration via pydantic-settings.

All values are read from environment variables.  The Settings object is built
once and cached — call get_settings() everywhere instead of instantiating
Settings directly so the lru_cache is honoured.
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str
    # asyncpg uses postgresql+asyncpg:// — normalise if caller uses postgres://
    @field_validator("database_url", mode="before")
    @classmethod
    def normalise_db_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_url: str

    # ── Keycloak ───────────────────────────────────────────────────────────────
    keycloak_url: str = "http://keycloak:8080/auth"
    keycloak_realm: str = "agentcompany"
    keycloak_client_id: str = "agent-runtime"
    keycloak_client_secret: str = ""

    # ── Meilisearch ────────────────────────────────────────────────────────────
    meilisearch_url: str = "http://meilisearch:7700"
    meilisearch_master_key: str = ""

    # ── Application ────────────────────────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    secret_key: str  # 32-byte hex; used for internal HMAC operations
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost"]

    # ── Runtime tuning ─────────────────────────────────────────────────────────
    max_concurrent_agents: int = 50

    # ── Webhooks ───────────────────────────────────────────────────────────────
    webhook_secret_plane: str = ""
    webhook_secret_mattermost: str = ""
    webhook_secret_outline: str = ""

    # ── External tool base URLs ────────────────────────────────────────────────
    plane_base_url: str = ""
    mattermost_base_url: str = ""
    outline_base_url: str = ""

    @property
    def jwks_uri(self) -> str:
        return (
            f"{self.keycloak_url}/realms/{self.keycloak_realm}"
            "/protocol/openid-connect/certs"
        )

    @property
    def token_issuer(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

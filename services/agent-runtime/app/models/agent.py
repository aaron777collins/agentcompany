"""Agent ORM model.

An agent is an AI entity that belongs to a company, holds a role, and
executes tasks.  Each agent has its own Keycloak service account.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_ulid


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("company_id", "slug", name="uq_agents_company_slug"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: f"agt_{generate_ulid()}"
    )
    org_id: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[str] = mapped_column(
        Text, ForeignKey("companies.id"), nullable=False
    )
    role_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("roles.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    # "idle" | "active" | "paused" | "error" | "starting" | "stopping"
    status: Mapped[str] = mapped_column(Text, nullable=False, default="idle")
    # Keycloak client for this agent's machine-to-machine JWT
    keycloak_client_id: Mapped[str | None] = mapped_column(
        Text, nullable=True, unique=True
    )
    llm_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Points to an agent_configs row — null if no versioned config yet
    system_prompt_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tool_permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Budget limits — null means unlimited
    token_budget_daily: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_budget_monthly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    company: Mapped["Company"] = relationship(  # type: ignore[name-defined]
        "Company", back_populates="agents"
    )
    role: Mapped["Role | None"] = relationship(  # type: ignore[name-defined]
        "Role", back_populates="agents"
    )

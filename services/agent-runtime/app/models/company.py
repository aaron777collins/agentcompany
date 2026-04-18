"""Company ORM model.

A company is the top-level container for agents, roles, and tasks.  It belongs
to an org (Keycloak tenant) and maps 1:1 to a virtual AI-powered organization.
"""

from sqlalchemy import Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_ulid


class Company(Base, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_companies_org_slug"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: f"cmp_{generate_ulid()}"
    )
    org_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="provisioning")
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Optimistic concurrency — callers must increment and check this
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Relationships (lazy="select" keeps queries explicit)
    agents: Mapped[list["Agent"]] = relationship(  # type: ignore[name-defined]
        "Agent", back_populates="company", lazy="select"
    )
    roles: Mapped[list["Role"]] = relationship(  # type: ignore[name-defined]
        "Role", back_populates="company", lazy="select"
    )
    tasks: Mapped[list["Task"]] = relationship(  # type: ignore[name-defined]
        "Task", back_populates="company", lazy="select"
    )

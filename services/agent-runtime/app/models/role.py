"""Role ORM model.

A role defines the position of an agent or human in the org chart, together
with the permissions and tool access they are granted.
"""

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_ulid


class Role(Base, TimestampMixin):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("company_id", "slug", name="uq_roles_company_slug"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: f"rol_{generate_ulid()}"
    )
    org_id: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[str] = mapped_column(
        Text, ForeignKey("companies.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Numeric level in the org chart: 0 = IC, higher = more senior
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reports_to_role_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("roles.id"), nullable=True
    )
    permissions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tool_access: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    max_headcount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # "agent" | "human" | "mixed"
    headcount_type: Mapped[str] = mapped_column(Text, nullable=False, default="agent")

    company: Mapped["Company"] = relationship(  # type: ignore[name-defined]
        "Company", back_populates="roles"
    )
    agents: Mapped[list["Agent"]] = relationship(  # type: ignore[name-defined]
        "Agent", back_populates="role"
    )
    # Self-referential: a role reports to another role
    reports_to: Mapped["Role | None"] = relationship(
        "Role", remote_side="Role.id", foreign_keys=[reports_to_role_id]
    )

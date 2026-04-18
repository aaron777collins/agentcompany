"""Event / audit-log ORM model.

Events are immutable records of things that happened.  The table is append-only
by design — no UPDATE or DELETE operations are issued against it by the
application.  Use INSERT only.
"""

from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_ulid


class Event(Base):
    """Immutable platform event.  No TimestampMixin — we only need 'timestamp'."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: f"evt_{generate_ulid()}"
    )
    org_id: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g. "task.created", "agent.error", "tool.webhook"
    type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "agent" | "human" | "system"
    actor_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, default="agent-runtime"
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

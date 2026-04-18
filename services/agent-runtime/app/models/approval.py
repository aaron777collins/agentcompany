"""Approval ORM model.

Approvals represent human-in-the-loop gates: an agent proposes an action and
a human (or an admin policy) must approve or deny it before the action
executes.  Each row has a pending/approved/denied lifecycle.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_ulid


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: f"apr_{generate_ulid()}"
    )
    org_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    company_id: Mapped[str] = mapped_column(
        Text, ForeignKey("companies.id"), nullable=False, index=True
    )
    # The agent that is requesting approval
    agent_id: Mapped[str] = mapped_column(
        Text, ForeignKey("agents.id"), nullable=False
    )
    # Optional — the task this approval is linked to
    task_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("tasks.id"), nullable=True
    )
    # Short human-readable description of what the agent wants to do
    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Full structured payload of the proposed action (tool call args, etc.)
    action_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # "pending" | "approved" | "denied"
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    # Who approved or denied (user ID)
    decided_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Free-form note the reviewer can attach to an approval or denial
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

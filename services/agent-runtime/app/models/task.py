"""Task ORM model.

Tasks are the primary unit of work.  They mirror Plane issues; external_refs
stores Plane-side identifiers so we can do bidirectional sync.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_ulid


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: f"tsk_{generate_ulid()}"
    )
    org_id: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[str] = mapped_column(
        Text, ForeignKey("companies.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "open" | "in_progress" | "blocked" | "review" | "done" | "cancelled"
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    # "urgent" | "high" | "medium" | "low"
    priority: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    # Either an agent ID or a user ID
    assigned_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "agent" | "human"
    assigned_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Who created this task (agent or user ID)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    parent_task_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("tasks.id"), nullable=True
    )
    # {"plane_issue_id": "PL-42", "plane_issue_url": "..."}
    external_refs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    company: Mapped["Company"] = relationship(  # type: ignore[name-defined]
        "Company", back_populates="tasks"
    )
    subtasks: Mapped[list["Task"]] = relationship(
        "Task", foreign_keys=[parent_task_id]
    )

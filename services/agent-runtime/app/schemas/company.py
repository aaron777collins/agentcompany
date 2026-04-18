"""Pydantic schemas for Company resources."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CompanySettings(BaseModel):
    timezone: str = "UTC"
    default_language: str = "en"
    human_approval_required: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = Field(default=None, max_length=5000)
    settings: CompanySettings = Field(default_factory=CompanySettings)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    status: str | None = Field(default=None)
    settings: dict[str, Any] | None = None


class CompanyRead(BaseModel):
    id: str
    org_id: str
    name: str
    slug: str
    description: str | None
    status: str
    settings: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = {"from_attributes": True}

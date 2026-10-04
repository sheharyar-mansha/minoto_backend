"""Schemas for members (the reusable Contact roster)."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None


class MemberListItem(BaseModel):
    """Compact roster row."""

    id: str
    name: str
    email: str
    has_voice_sample: bool
    voice_duration_seconds: int | None = None
    voice_sample_url: str | None = None
    spoken_name: str | None = None

    model_config = {"from_attributes": True}


class MemberOut(MemberListItem):
    """Full contact detail."""

    spoken_name_source: str | None = None
    voice_recorded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

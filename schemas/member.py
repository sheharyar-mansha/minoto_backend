from datetime import date, datetime

from pydantic import BaseModel, Field


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str
    role: str | None = Field(default=None, max_length=128)
    member_since: date | None = None
    saved_to_directory: bool = True


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    role: str | None = Field(default=None, max_length=128)
    member_since: date | None = None
    saved_to_directory: bool | None = None
    avatar_url: str | None = Field(default=None, max_length=1024)
    has_voice_sample: bool | None = None
    voice_duration_seconds: int | None = Field(default=None, ge=0)


class MemberOut(BaseModel):
    id: str
    name: str
    email: str
    role: str | None
    member_since: date | None
    saved_to_directory: bool
    avatar_url: str | None
    has_voice_sample: bool
    voice_duration_seconds: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

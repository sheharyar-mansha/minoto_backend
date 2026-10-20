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

    # Login-account status (never the password itself — that comes from reveal).
    has_account: bool = False
    must_set_password: bool = False
    has_set_own_password: bool = False


class MemberCreatedOut(MemberOut):
    """Returned once when a member is created — includes the one-time temp password."""

    temp_password: str | None = None


class RevealPasswordRequest(BaseModel):
    owner_password: str = Field(min_length=1, max_length=128)


class ResetPasswordRequest(BaseModel):
    owner_password: str = Field(min_length=1, max_length=128)


class MemberPasswordOut(BaseModel):
    """Result of reveal/reset. `status`: 'pending' (temp usable) | 'set' (member
    chose their own) | 'none' (no account)."""

    member_id: str
    email: str
    status: str
    temp_password: str | None = None

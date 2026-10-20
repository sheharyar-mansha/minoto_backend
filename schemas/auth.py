from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)


class PrincipalOut(BaseModel):
    """The signed-in principal — the owner, or a read-only member account.

    Superset shape so the owner keeps every field it had before; members fill
    only id/email/full_name/role.
    """

    id: str
    email: str
    full_name: str
    role: str = "owner"  # "owner" | "member"
    default_export_format: str | None = None
    include_timestamps_default: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AuthSuccessResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "owner"  # "owner" | "member"
    must_set_password: bool = False
    user: PrincipalOut


class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

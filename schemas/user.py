from datetime import datetime

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    """The single app owner. No role and no voice fields (owners don't enroll)."""

    id: str
    email: str
    full_name: str
    default_export_format: str
    include_timestamps_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserMeOut(UserOut):
    pass


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    default_export_format: str | None = Field(default=None, max_length=32)
    include_timestamps_default: bool | None = None

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    default_export_format: str
    include_timestamps_default: bool
    avatar_url: str | None
    has_voice_sample: bool
    voice_duration_seconds: int | None
    # ORM column; excluded from JSON — public URL path is exposed only as voice_sample_url.
    voice_file_path: str | None = Field(default=None, exclude=True)
    voice_sample_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _sync_voice_sample_url_from_db(self) -> "UserOut":
        """Always derive playback path from persisted columns (single source of truth)."""
        if self.has_voice_sample and self.voice_file_path:
            self.voice_sample_url = self.voice_file_path
        else:
            self.voice_sample_url = None
        return self


class UserMeOut(UserOut):
    pass


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    default_export_format: str | None = Field(default=None, max_length=32)
    include_timestamps_default: bool | None = None


class UserAccountListItem(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    avatar_url: str | None
    has_voice_sample: bool = False
    voice_duration_seconds: int | None = None
    voice_file_path: str | None = Field(default=None, exclude=True)
    voice_sample_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _sync_voice_sample_url(self) -> "UserAccountListItem":
        path = getattr(self, "voice_file_path", None)
        if self.has_voice_sample and path:
            self.voice_sample_url = path
        return self

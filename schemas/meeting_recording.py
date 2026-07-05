from datetime import datetime

from pydantic import BaseModel, Field


class MeetingDeviceRecordingOut(BaseModel):
    id: str
    meeting_id: str
    uploader_user_id: str
    participant_member_id: str | None
    device_label: str | None
    media_path: str
    mime_type: str | None
    duration_seconds: int | None
    byte_size: int
    recording_started_at: datetime | None = None
    recording_ended_at: datetime | None = None
    created_at: datetime


class MeetingDeviceRecordingUploadQuery(BaseModel):
    duration_seconds: int | None = Field(default=None, ge=0)
    device_label: str | None = Field(default=None, max_length=128)
    recording_started_at: str | None = None
    recording_ended_at: str | None = None

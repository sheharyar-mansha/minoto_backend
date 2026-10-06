from datetime import datetime

from pydantic import BaseModel


class MeetingRecordingOut(BaseModel):
    """Metadata for the single audio file captured for a meeting."""

    id: str
    meeting_id: str
    media_path: str
    mime_type: str | None = None
    duration_seconds: int | None = None
    byte_size: int
    recording_started_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

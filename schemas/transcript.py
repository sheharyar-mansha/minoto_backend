from datetime import datetime

from pydantic import BaseModel, Field


class MeetingTranscriptSegmentOut(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    speaker_user_id: str
    speaker_label: str
    text: str
    confidence: float | None = None
    source_uploader_user_id: str
    matched_user_id: str | None = None
    match_score: float | None = None
    match_status: str


class MeetingTranscriptOut(BaseModel):
    meeting_id: str
    status: str
    generated_at: datetime | None = None
    merged_text: str | None = None
    error_message: str | None = None
    segments: list[MeetingTranscriptSegmentOut]

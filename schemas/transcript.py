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


class MeetingMinutesOut(BaseModel):
    summary: str = ""
    decisions: list[str] = Field(default_factory=list)
    action_items: list[dict] = Field(default_factory=list)


class MeetingTranscriptOut(BaseModel):
    meeting_id: str
    status: str
    pipeline_version: str | None = None
    pipeline_stage: str | None = None
    generated_at: datetime | None = None
    merged_text: str | None = None
    error_message: str | None = None
    minutes: MeetingMinutesOut | None = None
    segments: list[MeetingTranscriptSegmentOut]

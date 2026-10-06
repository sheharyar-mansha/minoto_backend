from datetime import datetime

from pydantic import BaseModel, Field


class MeetingTranscriptSegmentOut(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    text: str
    confidence: float | None = None
    matched_contact_id: str | None = None
    label_name: str  # name rendered in the app
    name_source: str  # 'spoken' | 'fallback'
    match_status: str  # 'matched' | 'unknown'
    match_score: float | None = None
    is_overlap: bool = False
    is_expunged: bool = False  # redacted by a spoken command — app renders it blue


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
    segments: list[MeetingTranscriptSegmentOut] = Field(default_factory=list)

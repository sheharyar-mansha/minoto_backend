from datetime import date, datetime

from pydantic import BaseModel, Field

from schemas.member import MemberListItem

# Accepts "HH:MM" or "HH:MM:SS"; stored as "HH:MM:SS".
_TIME_PATTERN = r"^\d{2}:\d{2}(:\d{2})?$"


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    meeting_date: date
    start_time: str = Field(pattern=_TIME_PATTERN, description="HH:MM or HH:MM:SS (24h)")
    duration_minutes: int = Field(ge=1, le=24 * 60)
    member_ids: list[str] = Field(default_factory=list)


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    meeting_date: date | None = None
    start_time: str | None = Field(default=None, pattern=_TIME_PATTERN)
    duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)


class MeetingMembersPut(BaseModel):
    """Replace a meeting's roster with these contact ids."""

    member_ids: list[str] = Field(default_factory=list)


class ContactPreview(BaseModel):
    id: str
    name: str

    model_config = {"from_attributes": True}


class MeetingListItemOut(BaseModel):
    id: str
    title: str
    date_label: str
    duration_label: str
    meeting_date: date
    start_time: str
    duration_minutes: int
    scheduled_at: datetime
    status: str
    contact_count: int = 0
    contact_preview: list[ContactPreview] = Field(default_factory=list)


class MeetingDetailOut(BaseModel):
    id: str
    title: str
    date_label: str
    duration_label: str
    meeting_date: date
    start_time: str
    duration_minutes: int
    scheduled_at: datetime
    status: str
    conducted_at: datetime | None = None
    final_elapsed_seconds: int | None = None
    has_recording: bool = False
    contact_count: int = 0
    members: list[MemberListItem] = Field(default_factory=list)


class MeetingStartCheckOut(BaseModel):
    ready: bool
    members_with_voice: list[MemberListItem] = Field(default_factory=list)
    members_without_voice: list[MemberListItem] = Field(default_factory=list)


class MeetingCompleteRequest(BaseModel):
    final_elapsed_seconds: int | None = Field(default=None, ge=0)


class MeetingCompleteResponse(BaseModel):
    id: str
    status: str
    conducted_at: datetime
    final_elapsed_seconds: int | None = None

from datetime import date, datetime

from pydantic import BaseModel, Field


class ParticipantPreviewOut(BaseModel):
    member_id: str
    name: str
    avatar_url: str | None = None
    is_new_for_meeting: bool = False


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    meeting_date: date
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$", description="HH:MM 24h")
    duration_minutes: int = Field(ge=1, le=24 * 60)
    status: str = Field(default="scheduled", pattern="^(draft|scheduled|in_progress|completed|cancelled)$")


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    meeting_date: date | None = None
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    status: str | None = Field(
        default=None, pattern="^(draft|scheduled|in_progress|completed|cancelled)$"
    )


class MeetingListItemOut(BaseModel):
    id: str
    title: str
    date_label: str
    duration_label: str
    meeting_date: date
    duration_minutes: int
    status: str
    participant_count: int = 0
    participant_preview: list[ParticipantPreviewOut] = Field(default_factory=list)


class MeetingDetailOut(BaseModel):
    id: str
    title: str
    date_display: str
    start_time: str
    duration_display: str
    meeting_date: date
    duration_minutes: int
    status: str
    existing_members_count: int
    new_members_count: int
    participant_avatar_urls: list[str | None]
    existing_preview_avatar_urls: list[str | None] = Field(
        default_factory=list,
        description="Existing members only; up to 3 random slots; length = min(3, existing_members_count).",
    )
    participant_member_ids: list[str]
    participant_roster: list[ParticipantPreviewOut] = Field(
        default_factory=list,
        description="All meeting participants with display fields for clients.",
    )


class MeetingParticipantsPut(BaseModel):
    """Replace meeting roster with participant user ids."""

    member_ids: list[str] = Field(default_factory=list)
    user_ids: list[str] = Field(default_factory=list)

    def resolved_user_ids(self) -> list[str]:
        return self.user_ids if self.user_ids else self.member_ids


class MeetingCompleteResponse(BaseModel):
    id: str
    status: str
    conducted_at: datetime
    final_elapsed_seconds: int | None = None
    target_seconds: int | None = None
    overtime_seconds: int | None = None

"""Shape Meeting ORM rows into API response schemas."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.meeting import Meeting
from schemas.meeting import (
    ContactPreview,
    MeetingDetailOut,
    MeetingListItemOut,
)
from schemas.member import MemberListItem
from utils.formatting import date_label, duration_label

_PREVIEW_LIMIT = 3


def load_meeting_with_contacts(db: Session, meeting_id: str) -> Meeting | None:
    """Load a meeting with its contacts and recording eagerly."""
    stmt = (
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(
            selectinload(Meeting.contacts),
            selectinload(Meeting.recording),
        )
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def meeting_list_item(m: Meeting) -> MeetingListItemOut:
    contacts = list(m.contacts)
    return MeetingListItemOut(
        id=m.id,
        title=m.title,
        date_label=date_label(m.meeting_date),
        duration_label=duration_label(m.duration_minutes),
        meeting_date=m.meeting_date,
        start_time=m.start_time,
        duration_minutes=m.duration_minutes,
        scheduled_at=m.scheduled_at,
        status=m.status,
        contact_count=len(contacts),
        contact_preview=[ContactPreview.model_validate(c) for c in contacts[:_PREVIEW_LIMIT]],
    )


def meeting_detail(m: Meeting) -> MeetingDetailOut:
    contacts = list(m.contacts)
    return MeetingDetailOut(
        id=m.id,
        title=m.title,
        date_label=date_label(m.meeting_date),
        duration_label=duration_label(m.duration_minutes),
        meeting_date=m.meeting_date,
        start_time=m.start_time,
        duration_minutes=m.duration_minutes,
        scheduled_at=m.scheduled_at,
        status=m.status,
        conducted_at=m.conducted_at,
        final_elapsed_seconds=m.final_elapsed_seconds,
        has_recording=m.recording is not None,
        contact_count=len(contacts),
        members=[MemberListItem.model_validate(c) for c in contacts],
    )

import random

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.meeting import Meeting
from models.meeting_participant import MeetingParticipant
from models.user import User
from schemas.meeting import MeetingDetailOut, MeetingListItemOut, ParticipantPreviewOut
from utils.formatting import date_label, duration_label


def meeting_list_item(m: Meeting) -> MeetingListItemOut:
    links = list(m.participants)
    preview: list[ParticipantPreviewOut] = []
    for ln in links[:3]:
        user = ln.user
        preview.append(
            ParticipantPreviewOut(
                member_id=ln.user_id,
                name=user.full_name,
                avatar_url=user.avatar_url,
                is_new_for_meeting=False,
            )
        )
    return MeetingListItemOut(
        id=m.id,
        title=m.title,
        date_label=date_label(m.meeting_date),
        duration_label=duration_label(m.duration_minutes),
        meeting_date=m.meeting_date,
        duration_minutes=m.duration_minutes,
        status=m.status,
        participant_count=len(links),
        participant_preview=preview,
    )


def meeting_detail(m: Meeting) -> MeetingDetailOut:
    links = list(m.participants)
    avatars: list[str | None] = []
    for ln in links[:3]:
        avatars.append(ln.user.avatar_url)
    while len(avatars) < 3:
        avatars.append(None)

    existing_preview = [ln.user.avatar_url for ln in links[: min(3, len(links))]]
    random.shuffle(existing_preview)

    roster = [
        ParticipantPreviewOut(
            member_id=ln.user_id,
            name=ln.user.full_name,
            avatar_url=ln.user.avatar_url,
            is_new_for_meeting=False,
        )
        for ln in links
    ]

    return MeetingDetailOut(
        id=m.id,
        title=m.title,
        date_display=date_label(m.meeting_date),
        start_time=m.start_time,
        duration_display=duration_label(m.duration_minutes),
        meeting_date=m.meeting_date,
        duration_minutes=m.duration_minutes,
        status=m.status,
        existing_members_count=len(links),
        new_members_count=0,
        participant_avatar_urls=avatars[:3],
        existing_preview_avatar_urls=existing_preview,
        participant_member_ids=[ln.user_id for ln in links],
        participant_roster=roster,
    )


def load_meeting_with_links(db: Session, meeting_id: str) -> Meeting | None:
    stmt = (
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(selectinload(Meeting.participants).selectinload(MeetingParticipant.user))
    )
    return db.execute(stmt).unique().scalar_one_or_none()

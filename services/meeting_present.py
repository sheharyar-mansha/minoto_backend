import random

from sqlalchemy.orm import Session, selectinload

from models.meeting import Meeting
from models.meeting_member_link import MeetingMemberLink
from schemas.meeting import MeetingDetailOut, MeetingListItemOut, ParticipantPreviewOut
from utils.formatting import date_label, duration_label


def meeting_list_item(m: Meeting) -> MeetingListItemOut:
    links = list(m.member_links)
    preview: list[ParticipantPreviewOut] = []
    for ln in links[:3]:
        mem = ln.member
        preview.append(
            ParticipantPreviewOut(
                member_id=ln.member_id,
                name=mem.name,
                avatar_url=mem.avatar_url,
                is_new_for_meeting=bool(ln.is_new_for_meeting),
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
    links = list(m.member_links)
    new_count = sum(1 for ln in links if ln.is_new_for_meeting)
    existing_count = sum(1 for ln in links if not ln.is_new_for_meeting)
    avatars: list[str | None] = []
    for ln in links[:3]:
        avatars.append(ln.member.avatar_url)
    while len(avatars) < 3:
        avatars.append(None)

    existing_links = [ln for ln in links if not ln.is_new_for_meeting]
    random.shuffle(existing_links)
    preview_n = min(3, len(existing_links))
    existing_preview = [existing_links[i].member.avatar_url for i in range(preview_n)]

    roster = [
        ParticipantPreviewOut(
            member_id=ln.member_id,
            name=ln.member.name,
            avatar_url=ln.member.avatar_url,
            is_new_for_meeting=bool(ln.is_new_for_meeting),
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
        existing_members_count=existing_count,
        new_members_count=new_count,
        participant_avatar_urls=avatars[:3],
        existing_preview_avatar_urls=existing_preview,
        participant_member_ids=[ln.member_id for ln in links],
        participant_roster=roster,
    )


def load_meeting_with_links(db: Session, meeting_id: str) -> Meeting | None:
    from sqlalchemy import select

    stmt = (
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(
            selectinload(Meeting.member_links).selectinload(MeetingMemberLink.member),
        )
    )
    return db.execute(stmt).unique().scalar_one_or_none()

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.meeting import Meeting
from models.meeting_participant import MeetingParticipant
from models.user import User


def is_participant_user(user: User) -> bool:
    role = (user.role or "").strip().lower()
    return role in ("participant", "member", "host")


def is_admin_user(user: User) -> bool:
    return (user.role or "").strip().lower() == "admin"


def can_access_meeting(meeting: Meeting, user: User, db: Session) -> bool:
    if meeting.user_id == user.id:
        return True
    if is_admin_user(user):
        return True
    if not is_participant_user(user):
        return False
    stmt = (
        select(func.count())
        .select_from(MeetingParticipant)
        .where(
            MeetingParticipant.meeting_id == meeting.id,
            MeetingParticipant.user_id == user.id,
        )
    )
    return (db.scalar(stmt) or 0) > 0


def participant_visibility_clause(user: User):
    if is_participant_user(user) and not is_admin_user(user):
        return Meeting.id.in_(
            select(MeetingParticipant.meeting_id).where(MeetingParticipant.user_id == user.id)
        )
    return Meeting.user_id == user.id

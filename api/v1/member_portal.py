"""Read-only self-service endpoints for a logged-in member (the user dashboard).

A member can only VIEW: their profile, their upcoming/conducted meetings, and a
conducted meeting's detail + transcript/minutes. No writes, no meeting control —
all of that stays owner-only. Mounted at ``/me`` so it never collides with the
owner's ``/members/{id}`` routes.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_member, pagination
from db.session import get_db
from models.contact import Contact
from models.meeting import Meeting
from schemas.meeting import MeetingDetailOut, MeetingListItemOut
from schemas.member import MemberOut
from schemas.transcript import MeetingTranscriptOut
from services.meeting_present import load_meeting_with_contacts, meeting_detail, meeting_list_item
from services.meeting_query import VALID_SCOPES, apply_meeting_filters, order_meetings
from services.transcript_present import serialize_transcript

router = APIRouter(prefix="/me", tags=["member-portal"])


@router.get("", response_model=MemberOut)
def get_my_profile(member: Annotated[Contact, Depends(get_current_member)]) -> MemberOut:
    return MemberOut.model_validate(member)


@router.get("/meetings", response_model=list[MeetingListItemOut])
def list_my_meetings(
    member: Annotated[Contact, Depends(get_current_member)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[tuple[int, int], Depends(pagination)],
    scope: Annotated[str, Query()] = "all",
    q: Annotated[str | None, Query(max_length=200)] = None,
    search_content: Annotated[bool, Query()] = False,
    participant: Annotated[str | None, Query(max_length=200)] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
) -> list[MeetingListItemOut]:
    if scope not in VALID_SCOPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid scope")
    skip, limit = page
    stmt = select(Meeting).where(Meeting.contacts.any(Contact.id == member.id))
    stmt = apply_meeting_filters(
        stmt,
        scope=scope,
        q=q,
        search_content=search_content,
        participant=participant,
        date_from=date_from,
        date_to=date_to,
    )
    stmt = order_meetings(stmt, scope)
    rows = db.scalars(stmt.offset(skip).limit(limit)).all()
    return [meeting_list_item(m) for m in rows]


def _my_meeting_or_404(db: Session, member: Contact, meeting_id: str) -> Meeting:
    m = load_meeting_with_contacts(db, meeting_id)
    if m is None or not any(c.id == member.id for c in m.contacts):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return m


@router.get("/meetings/{meeting_id}", response_model=MeetingDetailOut)
def get_my_meeting(
    meeting_id: str,
    member: Annotated[Contact, Depends(get_current_member)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetailOut:
    m = _my_meeting_or_404(db, member, meeting_id)
    return meeting_detail(m)


@router.get("/meetings/{meeting_id}/transcript", response_model=MeetingTranscriptOut)
def get_my_meeting_transcript(
    meeting_id: str,
    member: Annotated[Contact, Depends(get_current_member)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingTranscriptOut:
    _my_meeting_or_404(db, member, meeting_id)
    return serialize_transcript(db, meeting_id)

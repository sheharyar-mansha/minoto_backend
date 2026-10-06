from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_user, pagination
from db.session import get_db
from models.contact import Contact
from models.meeting import Meeting
from models.user import User
from schemas.meeting import (
    MeetingCompleteRequest,
    MeetingCompleteResponse,
    MeetingCreate,
    MeetingDetailOut,
    MeetingListItemOut,
    MeetingMembersPut,
    MeetingStartCheckOut,
    MeetingUpdate,
)
from schemas.member import MemberListItem
from services.meeting_present import load_meeting_with_contacts, meeting_detail, meeting_list_item
from services.transcript_jobs import run_generate_meeting_transcript_task
from utils.ids import new_id

router = APIRouter(prefix="/meetings", tags=["meetings"])

_SCOPE_STATUS = {"upcoming": "scheduled", "completed": "completed"}


def _normalize_time(raw: str) -> str:
    """Accept 'HH:MM' or 'HH:MM:SS'; store as 'HH:MM:SS'."""
    return raw if raw.count(":") == 2 else f"{raw}:00"


def _compute_scheduled_at(meeting_date, start_time: str) -> datetime:
    hh, mm, ss = (int(x) for x in _normalize_time(start_time).split(":"))
    return datetime.combine(meeting_date, datetime.min.time()).replace(
        hour=hh, minute=mm, second=ss
    )


def _resolve_contacts(db: Session, member_ids: list[str]) -> list[Contact]:
    """Load contacts for the given ids, rejecting any that don't exist."""
    unique_ids = list(dict.fromkeys(member_ids))
    if not unique_ids:
        return []
    contacts = db.scalars(select(Contact).where(Contact.id.in_(unique_ids))).all()
    found = {c.id for c in contacts}
    missing = [mid for mid in unique_ids if mid not in found]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown member ids: {', '.join(missing)}",
        )
    return list(contacts)


def _reload_detail(db: Session, meeting_id: str) -> MeetingDetailOut:
    loaded = load_meeting_with_contacts(db, meeting_id)
    assert loaded is not None
    return meeting_detail(loaded)


@router.get("", response_model=list[MeetingListItemOut])
def list_meetings(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[tuple[int, int], Depends(pagination)],
    scope: Annotated[str, Query()] = "all",
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[MeetingListItemOut]:
    if scope not in ("upcoming", "completed", "all"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid scope")
    skip, limit = page
    stmt = select(Meeting)
    if scope in _SCOPE_STATUS:
        stmt = stmt.where(Meeting.status == _SCOPE_STATUS[scope])
    if q and q.strip():
        stmt = stmt.where(Meeting.title.ilike(f"%{q.strip()}%"))
    # Upcoming reads soonest-first; history reads most-recent-first.
    if scope == "upcoming":
        stmt = stmt.order_by(Meeting.scheduled_at.asc())
    else:
        stmt = stmt.order_by(Meeting.scheduled_at.desc())
    rows = db.scalars(stmt.offset(skip).limit(limit)).all()
    return [meeting_list_item(m) for m in rows]


@router.post("", response_model=MeetingDetailOut, status_code=status.HTTP_201_CREATED)
def create_meeting(
    body: MeetingCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetailOut:
    scheduled_at = _compute_scheduled_at(body.meeting_date, body.start_time)
    if scheduled_at < datetime.now():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Meeting cannot be scheduled in the past",
        )
    contacts = _resolve_contacts(db, body.member_ids)
    m = Meeting(
        id=new_id(),
        title=body.title.strip(),
        meeting_date=body.meeting_date,
        start_time=_normalize_time(body.start_time),
        duration_minutes=body.duration_minutes,
        scheduled_at=scheduled_at,
        status="scheduled",
    )
    m.contacts = contacts
    db.add(m)
    db.commit()
    return _reload_detail(db, m.id)


@router.get("/{meeting_id}", response_model=MeetingDetailOut)
def get_meeting(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetailOut:
    m = load_meeting_with_contacts(db, meeting_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return meeting_detail(m)


@router.patch("/{meeting_id}", response_model=MeetingDetailOut)
def update_meeting(
    meeting_id: str,
    body: MeetingUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetailOut:
    m = db.get(Meeting, meeting_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if m.status == "completed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Completed meetings cannot be edited")

    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        m.title = str(data["title"]).strip()
    if "duration_minutes" in data and data["duration_minutes"] is not None:
        m.duration_minutes = data["duration_minutes"]
    new_date = data.get("meeting_date") if data.get("meeting_date") is not None else m.meeting_date
    new_time = data.get("start_time") if data.get("start_time") is not None else m.start_time
    if ("meeting_date" in data and data["meeting_date"] is not None) or (
        "start_time" in data and data["start_time"] is not None
    ):
        scheduled_at = _compute_scheduled_at(new_date, new_time)
        if scheduled_at < datetime.now():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Meeting cannot be scheduled in the past",
            )
        m.meeting_date = new_date
        m.start_time = _normalize_time(new_time)
        m.scheduled_at = scheduled_at

    db.add(m)
    db.commit()
    return _reload_detail(db, meeting_id)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    m = db.get(Meeting, meeting_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    db.delete(m)  # cascades to recording / transcript / segments / roster links
    db.commit()


@router.put("/{meeting_id}/members", response_model=MeetingDetailOut)
def replace_members(
    meeting_id: str,
    body: MeetingMembersPut,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetailOut:
    m = db.get(Meeting, meeting_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    m.contacts = _resolve_contacts(db, body.member_ids)
    db.add(m)
    db.commit()
    return _reload_detail(db, meeting_id)


@router.get("/{meeting_id}/start-check", response_model=MeetingStartCheckOut)
def start_check(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingStartCheckOut:
    """A meeting is ready to record once every attending contact has a voice sample."""
    m = load_meeting_with_contacts(db, meeting_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    with_voice = [c for c in m.contacts if c.has_voice_sample]
    without_voice = [c for c in m.contacts if not c.has_voice_sample]
    return MeetingStartCheckOut(
        ready=len(m.contacts) > 0 and not without_voice,
        members_with_voice=[MemberListItem.model_validate(c) for c in with_voice],
        members_without_voice=[MemberListItem.model_validate(c) for c in without_voice],
    )


@router.post("/{meeting_id}/complete", response_model=MeetingCompleteResponse)
def complete_meeting(
    meeting_id: str,
    body: MeetingCompleteRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> MeetingCompleteResponse:
    m = load_meeting_with_contacts(db, meeting_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    # Readiness is required to attribute the transcript to the right people.
    if not m.contacts or any(not c.has_voice_sample for c in m.contacts):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Every member must have a voice sample before completing",
        )

    now = datetime.now()
    m.status = "completed"
    m.conducted_at = now
    m.final_elapsed_seconds = body.final_elapsed_seconds
    db.add(m)
    db.commit()
    db.refresh(m)

    background_tasks.add_task(
        run_generate_meeting_transcript_task,
        meeting_id,
        now.isoformat(),
        m.final_elapsed_seconds,
    )
    return MeetingCompleteResponse(
        id=m.id,
        status=m.status,
        conducted_at=now,
        final_elapsed_seconds=m.final_elapsed_seconds,
    )

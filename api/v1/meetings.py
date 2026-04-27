from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session, selectinload

from api.deps import get_current_user, pagination
from db.session import SessionLocal, get_db
from models.meeting import Meeting
from models.meeting_live_session import MeetingLiveSession
from models.meeting_member_link import MeetingMemberLink
from models.member import Member
from models.user import User
from schemas.common import PageMeta, PaginatedResponse
from schemas.meeting import (
    MeetingCompleteResponse,
    MeetingCreate,
    MeetingDetailOut,
    MeetingListItemOut,
    MeetingParticipantsPut,
    MeetingUpdate,
)
from services.meeting_transcript import generate_meeting_transcript
from services.meeting_present import load_meeting_with_links, meeting_detail, meeting_list_item
from services.pagination import run_paginated
from utils.ids import new_id

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _generate_transcript_background(
    meeting_id: str,
    conducted_at_iso: str,
    final_elapsed_seconds: int | None,
) -> None:
    ca = datetime.fromisoformat(conducted_at_iso)
    db = SessionLocal()
    try:
        generate_meeting_transcript(
            db,
            meeting_id=meeting_id,
            conducted_at=ca,
            final_elapsed_seconds=final_elapsed_seconds,
        )
    finally:
        db.close()


def _is_member_user(user: User) -> bool:
    return (user.role or "").strip().lower() == "member"


def _member_visibility_exists_clause(user: User):
    email = (user.email or "").strip().lower()
    return exists(
        select(MeetingMemberLink.meeting_id)
        .join(Member, Member.id == MeetingMemberLink.member_id)
        .where(
            MeetingMemberLink.meeting_id == Meeting.id,
            func.lower(Member.email) == email,
        )
    )


@router.get("", response_model=PaginatedResponse[MeetingListItemOut])
def list_meetings(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[tuple[int, int], Depends(pagination)],
    scope: Annotated[str, Query()] = "all",
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> PaginatedResponse[MeetingListItemOut]:
    if scope not in ("upcoming", "conducted", "all"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid scope")
    skip, limit = page
    visibility = (
        _member_visibility_exists_clause(user)
        if _is_member_user(user)
        else (Meeting.user_id == user.id)
    )
    stmt = (
        select(Meeting)
        .where(visibility)
        .options(
            selectinload(Meeting.member_links).selectinload(MeetingMemberLink.member),
        )
    )
    if scope == "upcoming":
        stmt = stmt.where(Meeting.status.in_(("draft", "scheduled", "in_progress")))
    elif scope == "conducted":
        stmt = stmt.where(Meeting.status == "completed")
    if q:
        stmt = stmt.where(Meeting.title.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(Meeting.meeting_date, Meeting.start_time)
    rows, total = run_paginated(db, stmt, skip=skip, limit=limit)
    return PaginatedResponse(
        items=[meeting_list_item(m) for m in rows],
        meta=PageMeta(total=total, skip=skip, limit=limit),
    )


@router.post("", response_model=MeetingDetailOut, status_code=status.HTTP_201_CREATED)
def create_meeting(
    body: MeetingCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetailOut:
    m = Meeting(
        id=new_id(),
        user_id=user.id,
        title=body.title.strip(),
        meeting_date=body.meeting_date,
        start_time=body.start_time,
        duration_minutes=body.duration_minutes,
        status=body.status,
    )
    db.add(m)
    db.commit()
    loaded = load_meeting_with_links(db, m.id)
    assert loaded is not None
    return meeting_detail(loaded)


@router.get("/{meeting_id}", response_model=MeetingDetailOut)
def get_meeting(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetailOut:
    m = load_meeting_with_links(db, meeting_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if m.user_id == user.id:
        return meeting_detail(m)
    if _is_member_user(user):
        current_email = (user.email or "").strip().lower()
        assigned = any(
            ((link.member.email if link.member is not None else "") or "").strip().lower()
            == current_email
            for link in m.member_links
        )
        if assigned:
            return meeting_detail(m)
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")


@router.patch("/{meeting_id}", response_model=MeetingDetailOut)
def update_meeting(
    meeting_id: str,
    body: MeetingUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetailOut:
    m = db.get(Meeting, meeting_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if m.status == "completed":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Completed meetings cannot be edited",
        )
    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        data["title"] = str(data["title"]).strip()
    for k, v in data.items():
        setattr(m, k, v)
    db.add(m)
    db.commit()
    loaded = load_meeting_with_links(db, meeting_id)
    assert loaded is not None
    return meeting_detail(loaded)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    m = db.get(Meeting, meeting_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    db.delete(m)
    db.commit()


@router.put("/{meeting_id}/participants", response_model=MeetingDetailOut)
def replace_participants(
    meeting_id: str,
    body: MeetingParticipantsPut,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetailOut:
    m = db.get(Meeting, meeting_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    db.execute(delete(MeetingMemberLink).where(MeetingMemberLink.meeting_id == meeting_id))
    seen: set[str] = set()
    for mid in body.member_ids:
        if mid in seen:
            continue
        seen.add(mid)
        mem = db.get(Member, mid)
        if mem is None or mem.user_id != user.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid member_id: {mid}",
            )
        # "New" for this meeting = no enrolled voice sample yet (first-time / needs recording).
        is_new = not mem.has_voice_sample
        db.add(
            MeetingMemberLink(
                meeting_id=meeting_id,
                member_id=mid,
                is_new_for_meeting=is_new,
            )
        )
    db.commit()
    loaded = load_meeting_with_links(db, meeting_id)
    assert loaded is not None
    return meeting_detail(loaded)


@router.post("/{meeting_id}/complete", response_model=MeetingCompleteResponse)
def complete_meeting(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> MeetingCompleteResponse:
    m = db.get(Meeting, meeting_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    final_elapsed_seconds: int | None = None
    target_seconds = int(m.duration_minutes * 60)
    overtime_seconds: int | None = None
    session_row = db.get(MeetingLiveSession, user.id)
    if session_row is not None and session_row.meeting_id == meeting_id:
        final_elapsed_seconds = int(session_row.elapsed_seconds)
        if (not session_row.is_paused) and session_row.running_since_ms is not None:
            now_ms = int(datetime.now().timestamp() * 1000)
            delta = max(0, (now_ms - int(session_row.running_since_ms)) // 1000)
            final_elapsed_seconds += int(delta)
        overtime_seconds = max(0, final_elapsed_seconds - target_seconds)
        db.delete(session_row)
    now = datetime.now()
    m.status = "completed"
    m.conducted_at = now
    db.add(m)
    db.commit()
    db.refresh(m)
    ca = m.conducted_at or now
    conducted_iso = ca.isoformat()
    background_tasks.add_task(
        _generate_transcript_background,
        meeting_id,
        conducted_iso,
        final_elapsed_seconds,
    )
    return MeetingCompleteResponse(
        id=m.id,
        status=m.status,
        conducted_at=ca,
        final_elapsed_seconds=final_elapsed_seconds,
        target_seconds=target_seconds,
        overtime_seconds=overtime_seconds,
    )

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.meeting import Meeting
from models.meeting_live_session import MeetingLiveSession
from models.user import User
from schemas.session import LiveSessionOut, LiveSessionUpsert
from services.meeting_access import can_access_meeting

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _live_session_out(row: MeetingLiveSession) -> LiveSessionOut:
    server_ms = int(datetime.now().timestamp() * 1000)
    if row.is_paused or row.running_since_ms is None:
        display_elapsed = int(row.elapsed_seconds)
    else:
        delta = max(0, server_ms - int(row.running_since_ms))
        display_elapsed = int(row.elapsed_seconds) + delta // 1000
    return LiveSessionOut(
        meeting_id=row.meeting_id,
        title=row.title,
        elapsed_seconds=int(row.elapsed_seconds),
        is_paused=bool(row.is_paused),
        running_since_ms=row.running_since_ms,
        total_target_seconds=int(row.total_target_seconds),
        server_now_ms=server_ms,
        display_elapsed_seconds=display_elapsed,
    )


def _can_access_meeting(meeting: Meeting, user: User, db: Session) -> bool:
    return can_access_meeting(meeting, user, db)


@router.get("/active", response_model=LiveSessionOut | None)
def get_active(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LiveSessionOut | None:
    row = db.get(MeetingLiveSession, user.id)
    if row is None:
        return None
    return _live_session_out(row)


@router.get("/meetings/{meeting_id}/active", response_model=LiveSessionOut | None)
def get_active_for_meeting(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LiveSessionOut | None:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if not _can_access_meeting(meeting, user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed for this meeting")

    # The owner row is the source of truth for all participants.
    row = db.get(MeetingLiveSession, meeting.user_id)
    if row is None or row.meeting_id != meeting_id:
        return None
    return _live_session_out(row)


@router.put("/active", response_model=LiveSessionOut)
def upsert_active(
    body: LiveSessionUpsert,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LiveSessionOut:
    m = db.get(Meeting, body.meeting_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    server_ms = int(datetime.now().timestamp() * 1000)
    row = db.get(MeetingLiveSession, user.id)
    if row is None:
        row = MeetingLiveSession(
            user_id=user.id,
            meeting_id=body.meeting_id,
            title=body.title.strip(),
            elapsed_seconds=body.elapsed_seconds,
            is_paused=body.is_paused,
            running_since_ms=None if body.is_paused else server_ms,
            total_target_seconds=body.total_target_seconds,
        )
        db.add(row)
    else:
        row.meeting_id = body.meeting_id
        row.title = body.title.strip()
        row.elapsed_seconds = body.elapsed_seconds
        row.is_paused = body.is_paused
        row.running_since_ms = None if body.is_paused else server_ms
        row.total_target_seconds = body.total_target_seconds
        db.add(row)
    if m.status in ("draft", "scheduled"):
        m.status = "in_progress"
        db.add(m)
    db.commit()
    db.refresh(row)
    return _live_session_out(row)


@router.delete("/active", status_code=status.HTTP_204_NO_CONTENT)
def clear_active(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    row = db.get(MeetingLiveSession, user.id)
    if row is not None:
        db.delete(row)
        db.commit()

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.meeting import Meeting
from models.meeting_live_session import MeetingLiveSession
from models.user import User
from schemas.session import LiveSessionOut, LiveSessionUpsert

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/active", response_model=LiveSessionOut | None)
def get_active(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LiveSessionOut | None:
    row = db.get(MeetingLiveSession, user.id)
    if row is None:
        return None
    return LiveSessionOut(
        meeting_id=row.meeting_id,
        title=row.title,
        elapsed_seconds=row.elapsed_seconds,
        is_paused=row.is_paused,
        running_since_ms=row.running_since_ms,
        total_target_seconds=row.total_target_seconds,
    )


@router.put("/active", response_model=LiveSessionOut)
def upsert_active(
    body: LiveSessionUpsert,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LiveSessionOut:
    m = db.get(Meeting, body.meeting_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    row = db.get(MeetingLiveSession, user.id)
    if row is None:
        row = MeetingLiveSession(
            user_id=user.id,
            meeting_id=body.meeting_id,
            title=body.title.strip(),
            elapsed_seconds=body.elapsed_seconds,
            is_paused=body.is_paused,
            running_since_ms=body.running_since_ms,
            total_target_seconds=body.total_target_seconds,
        )
        db.add(row)
    else:
        row.meeting_id = body.meeting_id
        row.title = body.title.strip()
        row.elapsed_seconds = body.elapsed_seconds
        row.is_paused = body.is_paused
        row.running_since_ms = body.running_since_ms
        row.total_target_seconds = body.total_target_seconds
        db.add(row)
    db.commit()
    db.refresh(row)
    return LiveSessionOut(
        meeting_id=row.meeting_id,
        title=row.title,
        elapsed_seconds=row.elapsed_seconds,
        is_paused=row.is_paused,
        running_since_ms=row.running_since_ms,
        total_target_seconds=row.total_target_seconds,
    )


@router.delete("/active", status_code=status.HTTP_204_NO_CONTENT)
def clear_active(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    row = db.get(MeetingLiveSession, user.id)
    if row is not None:
        db.delete(row)
        db.commit()

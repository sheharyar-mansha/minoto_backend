from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_user
from config.settings import UPLOAD_DIR
from db.session import get_db
from models.meeting import Meeting
from models.meeting_recording import MeetingRecording
from models.user import User
from schemas.meeting_recording import MeetingRecordingOut
from services.storage import remove_file_if_exists, save_streaming_upload
from utils.ids import new_id

router = APIRouter(prefix="/meetings", tags=["meeting-recordings"])

_MIN_RECORDING_BYTES = 128


def _ext_from_upload(file: UploadFile) -> str:
    ext = Path(file.filename or "recording.m4a").suffix.lower()
    if not ext or len(ext) > 8:
        return ".m4a"
    return ext


def _get_recording(db: Session, meeting_id: str) -> MeetingRecording | None:
    return db.scalars(
        select(MeetingRecording).where(MeetingRecording.meeting_id == meeting_id)
    ).first()


@router.post(
    "/{meeting_id}/recording",
    response_model=MeetingRecordingOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_meeting_recording(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    duration_seconds: Annotated[int | None, Query(ge=0)] = None,
) -> MeetingRecordingOut:
    """Store the meeting's single audio file, replacing any previous one."""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    ext = _ext_from_upload(file)
    rel = f"meeting_recordings/{meeting_id}/{new_id()}{ext}"
    dest = UPLOAD_DIR / rel
    save_streaming_upload(file, dest)
    size = int(dest.stat().st_size)
    if size < _MIN_RECORDING_BYTES:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Recording file is too small")

    existing = _get_recording(db, meeting_id)
    if existing is not None:
        remove_file_if_exists(existing.file_path)
        existing.file_path = rel
        existing.mime_type = file.content_type
        existing.duration_seconds = duration_seconds
        existing.byte_size = size
        row = existing
    else:
        row = MeetingRecording(
            id=new_id(),
            meeting_id=meeting_id,
            file_path=rel,
            mime_type=file.content_type,
            duration_seconds=duration_seconds,
            byte_size=size,
        )
    db.add(row)
    db.commit()
    db.refresh(row)
    return MeetingRecordingOut.model_validate(row)


@router.get("/{meeting_id}/recording", response_model=MeetingRecordingOut)
def get_meeting_recording(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingRecordingOut:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    row = _get_recording(db, meeting_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No recording for this meeting")
    return MeetingRecordingOut.model_validate(row)

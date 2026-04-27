from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_current_user
from config.settings import UPLOAD_DIR
from db.session import get_db
from models.meeting import Meeting
from models.meeting_device_recording import MeetingDeviceRecording
from models.meeting_member_link import MeetingMemberLink
from models.member import Member
from models.user import User
from schemas.meeting_recording import MeetingDeviceRecordingOut
from services.storage import save_streaming_upload
from utils.ids import new_id

router = APIRouter(prefix="/meetings", tags=["meeting-recordings"])


def _is_member_user(user: User) -> bool:
    return (user.role or "").strip().lower() == "member"


def _can_access_meeting(meeting: Meeting, user: User, db: Session) -> bool:
    if meeting.user_id == user.id:
        return True
    if not _is_member_user(user):
        return False
    email = (user.email or "").strip().lower()
    assigned_stmt = (
        select(func.count())
        .select_from(MeetingMemberLink)
        .join(Member, Member.id == MeetingMemberLink.member_id)
        .where(
            MeetingMemberLink.meeting_id == meeting.id,
            func.lower(Member.email) == email,
        )
    )
    return (db.scalar(assigned_stmt) or 0) > 0


def _ext_from_upload(file: UploadFile) -> str:
    ext = Path(file.filename or "sample.m4a").suffix.lower()
    if not ext or len(ext) > 8:
        return ".m4a"
    return ext


def _to_out(row: MeetingDeviceRecording) -> MeetingDeviceRecordingOut:
    return MeetingDeviceRecordingOut(
        id=row.id,
        meeting_id=row.meeting_id,
        uploader_user_id=row.uploader_user_id,
        participant_member_id=row.participant_member_id,
        device_label=row.device_label,
        media_path=row.file_path,
        mime_type=row.mime_type,
        duration_seconds=row.duration_seconds,
        byte_size=row.byte_size,
        created_at=row.created_at,
    )


@router.post(
    "/{meeting_id}/recordings",
    response_model=MeetingDeviceRecordingOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_meeting_recording(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    duration_seconds: Annotated[int | None, Query(ge=0)] = None,
    device_label: Annotated[str | None, Query(max_length=128)] = None,
) -> MeetingDeviceRecordingOut:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if not _can_access_meeting(meeting, user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed for this meeting")

    ext = _ext_from_upload(file)
    rel = f"meeting_recordings/{meeting_id}/{user.id}/{new_id()}{ext}"
    dest = UPLOAD_DIR / rel
    save_streaming_upload(file, dest)
    size = int(dest.stat().st_size)
    if size < 128:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Recording file is too small")

    row = MeetingDeviceRecording(
        id=new_id(),
        meeting_id=meeting_id,
        uploader_user_id=user.id,
        participant_member_id=None,
        device_label=device_label.strip() if device_label else None,
        file_path=rel,
        mime_type=file.content_type,
        duration_seconds=duration_seconds,
        byte_size=size,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get(
    "/{meeting_id}/recordings",
    response_model=list[MeetingDeviceRecordingOut],
)
def list_meeting_recordings(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[MeetingDeviceRecordingOut]:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if not _can_access_meeting(meeting, user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed for this meeting")

    stmt = select(MeetingDeviceRecording).where(MeetingDeviceRecording.meeting_id == meeting_id)
    # Members can inspect only their own uploads; owner can inspect all.
    if meeting.user_id != user.id:
        stmt = stmt.where(MeetingDeviceRecording.uploader_user_id == user.id)
    rows = db.scalars(stmt.order_by(MeetingDeviceRecording.created_at.asc())).all()
    return [_to_out(r) for r in rows]

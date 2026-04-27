from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import SessionLocal, get_db
from models.meeting import Meeting
from models.meeting_member_link import MeetingMemberLink
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from models.member import Member
from models.user import User
from schemas.transcript import MeetingTranscriptOut, MeetingTranscriptSegmentOut
from services.meeting_transcript import generate_meeting_transcript

router = APIRouter(prefix="/meetings", tags=["meeting-transcripts"])


def _regenerate_transcript_background(meeting_id: str, conducted_at_iso: str) -> None:
    db = SessionLocal()
    try:
        ca = datetime.fromisoformat(conducted_at_iso)
        generate_meeting_transcript(
            db,
            meeting_id=meeting_id,
            conducted_at=ca,
            final_elapsed_seconds=None,
        )
    finally:
        db.close()


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


@router.get("/{meeting_id}/transcript", response_model=MeetingTranscriptOut)
def get_meeting_transcript(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingTranscriptOut:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if not _can_access_meeting(meeting, user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed for this meeting")

    t = db.get(MeetingTranscript, meeting_id)
    if t is None:
        return MeetingTranscriptOut(
            meeting_id=meeting_id,
            status="pending",
            generated_at=None,
            merged_text=None,
            error_message=None,
            segments=[],
        )
    rows = db.scalars(
        select(MeetingTranscriptSegment)
        .where(MeetingTranscriptSegment.meeting_id == meeting_id)
        .order_by(
            MeetingTranscriptSegment.start_sec.asc(),
            MeetingTranscriptSegment.uploader_user_id.asc(),
            MeetingTranscriptSegment.end_sec.asc(),
        )
    ).all()
    users = {
        u.id: u.full_name
        for u in db.scalars(
            select(User).where(
                User.id.in_(
                    [r.uploader_user_id for r in rows]
                    + [r.matched_user_id for r in rows if r.matched_user_id]
                )
            )
        ).all()
    }
    return MeetingTranscriptOut(
        meeting_id=meeting_id,
        status=t.status,
        generated_at=t.generated_at,
        merged_text=t.merged_text,
        error_message=t.error_message,
        segments=[
            MeetingTranscriptSegmentOut(
                start_sec=float(r.start_sec),
                end_sec=float(r.end_sec),
                speaker_user_id=r.matched_user_id or r.uploader_user_id,
                speaker_label=(
                    "Unknown"
                    if r.match_status == "unknown"
                    else users.get(r.matched_user_id or r.uploader_user_id, "Unknown")
                ),
                text=r.text,
                confidence=r.confidence,
                source_uploader_user_id=r.source_uploader_user_id or r.uploader_user_id,
                matched_user_id=r.matched_user_id,
                match_score=r.match_score,
                match_status=r.match_status,
            )
            for r in rows
        ],
    )


@router.post(
    "/{meeting_id}/transcript/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run transcription (meeting owner, completed meetings only)",
)
def regenerate_meeting_transcript(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Use when the first run produced no lines but recordings exist (e.g. race or VAD)."""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if meeting.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the host can regenerate")
    if meeting.status != "completed" or meeting.conducted_at is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Only completed meetings with a conducted time can be regenerated",
        )
    conducted_iso = meeting.conducted_at.isoformat()
    background_tasks.add_task(_regenerate_transcript_background, meeting_id, conducted_iso)
    return {"status": "processing"}

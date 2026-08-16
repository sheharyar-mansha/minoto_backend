from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.meeting import Meeting
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from models.user import User
from schemas.transcript import MeetingMinutesOut, MeetingTranscriptOut, MeetingTranscriptSegmentOut
from services.meeting_access import can_access_meeting
from services.transcript_jobs import run_generate_meeting_transcript_task

router = APIRouter(prefix="/meetings", tags=["meeting-transcripts"])


@router.get("/{meeting_id}/transcript", response_model=MeetingTranscriptOut)
def get_meeting_transcript(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingTranscriptOut:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if not can_access_meeting(meeting, user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed for this meeting")

    t = db.get(MeetingTranscript, meeting_id)
    if t is None:
        return MeetingTranscriptOut(
            meeting_id=meeting_id,
            status="pending",
            pipeline_version=None,
            pipeline_stage=None,
            generated_at=None,
            merged_text=None,
            error_message=None,
            minutes=None,
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
    user_ids = [r.uploader_user_id for r in rows]
    user_ids.extend([r.matched_user_id for r in rows if r.matched_user_id])
    users = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}

    minutes = None
    if t.minutes_json:
        import json

        try:
            parsed = json.loads(t.minutes_json)
            minutes = MeetingMinutesOut.model_validate(parsed)
        except Exception:
            minutes = None

    return MeetingTranscriptOut(
        meeting_id=meeting_id,
        status=t.status,
        pipeline_version=t.pipeline_version,
        pipeline_stage=t.pipeline_stage,
        generated_at=t.generated_at,
        merged_text=t.merged_text,
        error_message=t.error_message,
        minutes=minutes,
        segments=[
            MeetingTranscriptSegmentOut(
                # Cross-device clock sync can produce slightly negative times; clamp for API.
                start_sec=max(0.0, float(r.start_sec)),
                end_sec=max(0.0, float(r.end_sec)),
                speaker_user_id=r.matched_user_id or r.uploader_user_id,
                speaker_label=(
                    "Unknown"
                    if r.match_status in {"unknown", "outsider"}
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


@router.post("/{meeting_id}/transcript/regenerate", status_code=status.HTTP_202_ACCEPTED)
def regenerate_meeting_transcript(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
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
    tx = db.get(MeetingTranscript, meeting_id)
    if tx is None:
        tx = MeetingTranscript(meeting_id=meeting_id, status="processing", pipeline_stage="queued")
        db.add(tx)
    else:
        tx.status = "processing"
        tx.pipeline_stage = "queued"
        tx.error_message = None
    db.commit()
    background_tasks.add_task(
        run_generate_meeting_transcript_task,
        meeting_id,
        meeting.conducted_at.isoformat(),
        meeting.final_elapsed_seconds,
    )
    return {"status": "processing"}

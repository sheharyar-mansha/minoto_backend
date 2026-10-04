import json
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
from schemas.transcript import (
    MeetingMinutesOut,
    MeetingTranscriptOut,
    MeetingTranscriptSegmentOut,
)
from services.transcript_jobs import run_generate_meeting_transcript_task

router = APIRouter(prefix="/meetings", tags=["meeting-transcripts"])


def _parse_minutes(raw: str | None) -> MeetingMinutesOut | None:
    if not raw:
        return None
    try:
        return MeetingMinutesOut.model_validate(json.loads(raw))
    except Exception:
        return None


@router.get("/{meeting_id}/transcript", response_model=MeetingTranscriptOut)
def get_meeting_transcript(
    meeting_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingTranscriptOut:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    t = db.get(MeetingTranscript, meeting_id)
    if t is None:
        return MeetingTranscriptOut(meeting_id=meeting_id, status="pending")

    rows = db.scalars(
        select(MeetingTranscriptSegment)
        .where(MeetingTranscriptSegment.meeting_id == meeting_id)
        .order_by(
            MeetingTranscriptSegment.start_sec.asc(),
            MeetingTranscriptSegment.end_sec.asc(),
        )
    ).all()

    return MeetingTranscriptOut(
        meeting_id=meeting_id,
        status=t.status,
        pipeline_version=t.pipeline_version,
        pipeline_stage=t.pipeline_stage,
        generated_at=t.generated_at,
        merged_text=t.merged_text,
        error_message=t.error_message,
        minutes=_parse_minutes(t.minutes_json),
        segments=[
            MeetingTranscriptSegmentOut(
                start_sec=max(0.0, float(r.start_sec)),
                end_sec=max(0.0, float(r.end_sec)),
                text=r.text,
                confidence=r.confidence,
                matched_contact_id=r.matched_contact_id,
                label_name=r.label_name,
                name_source=r.name_source,
                match_status=r.match_status,
                match_score=r.match_score,
                is_overlap=bool(r.is_overlap),
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
    if meeting.status != "completed" or meeting.conducted_at is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Only completed meetings can have their transcript regenerated",
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

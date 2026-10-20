"""Serialize a meeting's transcript + minutes for the API.

Shared by the owner's `GET /meetings/{id}/transcript` and the member's read-only
`GET /members/me/meetings/{id}/transcript`.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from schemas.transcript import (
    MeetingMinutesOut,
    MeetingTranscriptOut,
    MeetingTranscriptSegmentOut,
)


def _parse_minutes(raw: str | None) -> MeetingMinutesOut | None:
    if not raw:
        return None
    try:
        return MeetingMinutesOut.model_validate(json.loads(raw))
    except Exception:
        return None


def serialize_transcript(db: Session, meeting_id: str) -> MeetingTranscriptOut:
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
        # Command utterances ("expunge …") are hidden; expunged statements are
        # returned (flagged) so the app can render them blue.
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
                is_expunged=bool(r.is_expunged),
            )
            for r in rows
            if not r.is_command
        ],
    )

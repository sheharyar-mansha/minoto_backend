from __future__ import annotations

import logging
import threading
from datetime import datetime

from db.session import SessionLocal
from models.meeting import Meeting
from models.meeting_transcript import MeetingTranscript
from pipeline.runner import generate_meeting_transcript

log = logging.getLogger(__name__)

_EMPTY_TRANSCRIPT_ERRORS = frozenset(
    {
        "No device recordings uploaded.",
        "Could not decode any recordings.",
    }
)

_in_flight: set[str] = set()
_in_flight_lock = threading.Lock()


def _resolve_final_elapsed_seconds(
    meeting: Meeting | None,
    final_elapsed_seconds: int | None,
) -> int | None:
    if final_elapsed_seconds is not None:
        return final_elapsed_seconds
    if meeting is not None and meeting.final_elapsed_seconds is not None:
        return int(meeting.final_elapsed_seconds)
    return None


def run_generate_meeting_transcript_task(
    meeting_id: str,
    conducted_at_iso: str,
    final_elapsed_seconds: int | None,
) -> None:
    with _in_flight_lock:
        if meeting_id in _in_flight:
            log.info("Transcript job already running for meeting=%s; skipping duplicate", meeting_id)
            return
        _in_flight.add(meeting_id)

    ca = datetime.fromisoformat(conducted_at_iso)
    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        elapsed = _resolve_final_elapsed_seconds(meeting, final_elapsed_seconds)
        generate_meeting_transcript(
            db,
            meeting_id=meeting_id,
            conducted_at=ca,
            final_elapsed_seconds=elapsed,
        )
    finally:
        db.close()
        with _in_flight_lock:
            _in_flight.discard(meeting_id)


def should_regenerate_transcript_after_upload(tx: MeetingTranscript | None) -> bool:
    if tx is None:
        return True
    if tx.status == "processing":
        return False
    if tx.status == "failed":
        return True
    if tx.status == "completed":
        if tx.error_message in _EMPTY_TRANSCRIPT_ERRORS:
            return True
        if not (tx.merged_text or "").strip() and not tx.minutes_json:
            return True
    return False

"""Background execution of the transcript pipeline.

Single-device flow: a meeting has exactly one recording, so there is no waiting
for multiple uploads. `complete` / `regenerate` enqueue this task, which opens its
own DB session and runs the (Phase-2 stub) pipeline runner. An in-flight guard
prevents the same meeting being processed twice concurrently.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from db.session import SessionLocal
from models.meeting import Meeting
from pipeline.runner import generate_meeting_transcript

log = logging.getLogger(__name__)

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
    """Run the pipeline for one meeting in a background worker."""
    with _in_flight_lock:
        if meeting_id in _in_flight:
            log.info("Transcript job already running for meeting=%s; skipping duplicate", meeting_id)
            return
        _in_flight.add(meeting_id)

    conducted_at = datetime.fromisoformat(conducted_at_iso)
    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        elapsed = _resolve_final_elapsed_seconds(meeting, final_elapsed_seconds)
        generate_meeting_transcript(
            db,
            meeting_id=meeting_id,
            conducted_at=conducted_at,
            final_elapsed_seconds=elapsed,
        )
    except Exception:
        log.exception("Transcript job crashed for meeting=%s", meeting_id)
    finally:
        db.close()
        with _in_flight_lock:
            _in_flight.discard(meeting_id)

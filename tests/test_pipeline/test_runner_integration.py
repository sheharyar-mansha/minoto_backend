"""End-to-end runner test on an in-memory DB with fake ASR/minutes (no models, no net).

Exercises the real orchestration: DB read -> lazy transcribe -> align -> cross-device
merge -> assemble -> persist segments + merged_text + minutes, and status transitions.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401  (import side effects register all tables with Base.metadata)
import pipeline.runner as runner
from db.base import Base
from models.meeting import Meeting
from models.meeting_device_recording import MeetingDeviceRecording
from models.meeting_participant import MeetingParticipant
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from models.user import User
from pipeline.types import MinutesDraft, TranscriptSegmentDraft

SR = 16000


class _FakeAsr:
    def __init__(self, by_recording):
        self.by_recording = by_recording

    def transcribe_file(self, audio, sr, recording_id, uploader_user_id, initial_prompt=None):
        return [
            TranscriptSegmentDraft(
                start_sec=s, end_sec=e, text=t,
                speaker_user_id=uploader_user_id,
                source_recording_id=recording_id,
                source_uploader_user_id=uploader_user_id,
                confidence=0.9, match_status="matched", words=[],
            )
            for (s, e, t) in self.by_recording.get(recording_id, [])
        ]


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _seed(db):
    db.add_all([
        User(id="ali", email="ali@x.com", full_name="Ali", hashed_password="x"),
        User(id="amna", email="amna@x.com", full_name="Amna", hashed_password="x"),
        Meeting(
            id="m1", user_id="ali", title="Standup", meeting_date=date(2026, 1, 1),
            start_time="10:00:00", duration_minutes=30, status="completed",
            conducted_at=datetime(2026, 1, 1, 10, 0, 0), final_elapsed_seconds=60,
        ),
        MeetingParticipant(meeting_id="m1", user_id="ali"),
        MeetingParticipant(meeting_id="m1", user_id="amna"),
        MeetingDeviceRecording(id="rec_ali", meeting_id="m1", uploader_user_id="ali", file_path="/fake/ali.m4a"),
        MeetingDeviceRecording(id="rec_amna", meeting_id="m1", uploader_user_id="amna", file_path="/fake/amna.m4a"),
    ])
    db.commit()


def test_pipeline_end_to_end_dedupes_and_persists(db, monkeypatch):
    _seed(db)

    # Ali says "Hi" then a unique line; Amna's phone only caught the faint echo of "Hi".
    fake_asr = _FakeAsr({
        "rec_ali": [(0.0, 2.0, "Hi"), (3.0, 6.0, "lets optimize the whole application today")],
        "rec_amna": [(0.0, 2.0, "Hi")],
    })
    amp = {"/fake/ali.m4a": 0.9, "/fake/amna.m4a": 0.2}
    loads: list[str] = []

    def fake_load(path):
        loads.append(str(path))
        return np.full(SR * 6, amp.get(str(path), 0.5), dtype=np.float32), SR

    monkeypatch.setattr(runner.settings, "PYANNOTE_AUTH_TOKEN", None)  # speaker matching off, deterministic
    monkeypatch.setattr(runner, "_resolve_path", lambda raw: Path(raw) if raw else None)  # skip on-disk check
    monkeypatch.setattr(runner, "get_asr_backend", lambda: fake_asr)
    monkeypatch.setattr(runner, "load_mono_wav", fake_load)
    monkeypatch.setattr(
        runner, "_wait_for_recordings",
        lambda db, mid, timeout: db.scalars(
            select(MeetingDeviceRecording)
            .where(MeetingDeviceRecording.meeting_id == mid)
            .order_by(MeetingDeviceRecording.created_at.asc())
        ).all(),
    )
    monkeypatch.setattr(runner, "generate_minutes", lambda segs, labels, title: MinutesDraft("summary here", ["ship it"], []))

    runner.generate_meeting_transcript(
        db, meeting_id="m1",
        conducted_at=datetime(2026, 1, 1, 10, 0, 0), final_elapsed_seconds=60,
    )

    tx = db.get(MeetingTranscript, "m1")
    assert tx.status == "completed"
    assert tx.pipeline_stage == "completed"

    segs = db.scalars(
        select(MeetingTranscriptSegment).where(MeetingTranscriptSegment.meeting_id == "m1")
    ).all()
    texts = sorted(s.text for s in segs)
    # The duplicated "Hi" (ali's phone + amna's echo) collapsed to a single line.
    assert texts == ["Hi", "lets optimize the whole application today"]

    assert tx.merged_text and "Hi" in tx.merged_text and "optimize" in tx.merged_text
    assert tx.minutes_json and "summary here" in tx.minutes_json
    # Lazy loader decoded each recording exactly once (speaker matching off -> no re-reads).
    assert sorted(loads) == ["/fake/ali.m4a", "/fake/amna.m4a"]


def test_pipeline_no_recordings_completes_empty(db, monkeypatch):
    db.add(Meeting(
        id="m2", user_id="ali", title="Empty", meeting_date=date(2026, 1, 1),
        start_time="10:00:00", duration_minutes=30, status="completed",
        conducted_at=datetime(2026, 1, 1, 10, 0, 0), final_elapsed_seconds=60,
    ))
    db.add(User(id="ali", email="ali@x.com", full_name="Ali", hashed_password="x"))
    db.commit()
    monkeypatch.setattr(runner, "_wait_for_recordings", lambda db, mid, timeout: [])

    runner.generate_meeting_transcript(
        db, meeting_id="m2",
        conducted_at=datetime(2026, 1, 1, 10, 0, 0), final_elapsed_seconds=60,
    )
    tx = db.get(MeetingTranscript, "m2")
    assert tx.status == "completed"
    assert tx.merged_text == ""
    assert tx.error_message == "No device recordings uploaded."

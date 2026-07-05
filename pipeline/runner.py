from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from config.settings import UPLOAD_DIR, settings
from models.meeting import Meeting
from models.meeting_device_recording import MeetingDeviceRecording
from models.meeting_participant import MeetingParticipant
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from models.user import User
from pipeline import PIPELINE_VERSION
from pipeline.align.gcc_phat import align_channels
from pipeline.asr.backends import get_asr_backend
from pipeline.assemble.timeline import assemble_timeline, format_merged_text
from pipeline.audio_io import load_mono_wav, probe_duration_sec
from pipeline.minutes.gemini_minutes import generate_minutes
from pipeline.select.channel_selection import select_best_channels
from pipeline.speaker.backends import deserialize_embedding, get_embedding_backend
from pipeline.speaker.verify import SpeakerRef, verify_speaker
from pipeline.types import ChannelRecording
from pipeline.vad.energy_vad import energy_vad_regions
from utils.ids import new_id

log = logging.getLogger(__name__)

_GRACE_SEC_AFTER_MEETING_END = 90.0
_RECORDINGS_STABLE_SEC = 15.0


def _as_py_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _resolve_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p
    c = UPLOAD_DIR / raw
    if c.exists():
        return c
    s = str(raw).replace("\\", "/").lstrip("/")
    if s.lower().startswith("uploads/"):
        c2 = UPLOAD_DIR / s.split("/", 1)[1]
        if c2.exists():
            return c2
    return c if c.exists() else None


def _wait_for_recordings(db: Session, meeting_id: str, timeout_sec: float) -> list[MeetingDeviceRecording]:
    """Wait for uploads to finish: require a quiet period after the latest recording."""
    deadline = time.monotonic() + timeout_sec
    last_count = 0
    stable_since: float | None = None

    while time.monotonic() < deadline:
        recs = db.scalars(
            select(MeetingDeviceRecording)
            .where(MeetingDeviceRecording.meeting_id == meeting_id)
            .order_by(MeetingDeviceRecording.created_at.asc())
        ).all()
        count = len(recs)
        if count == 0:
            stable_since = None
            last_count = 0
            _set_stage(db, meeting_id, "waiting_for_uploads")
        else:
            now = time.monotonic()
            if count != last_count:
                last_count = count
                stable_since = now
            elif stable_since is not None and (now - stable_since) >= _RECORDINGS_STABLE_SEC:
                return recs
        time.sleep(2.0)
        db.expire_all()

    return db.scalars(
        select(MeetingDeviceRecording)
        .where(MeetingDeviceRecording.meeting_id == meeting_id)
        .order_by(MeetingDeviceRecording.created_at.asc())
    ).all()


def _set_stage(db: Session, meeting_id: str, stage: str, status: str = "processing") -> None:
    row = db.get(MeetingTranscript, meeting_id)
    if row is None:
        row = MeetingTranscript(meeting_id=meeting_id, status=status, pipeline_stage=stage)
        db.add(row)
    else:
        row.status = status
        row.pipeline_stage = stage
    row.pipeline_version = PIPELINE_VERSION
    db.commit()


def generate_meeting_transcript(
    db: Session,
    *,
    meeting_id: str,
    conducted_at: datetime,
    final_elapsed_seconds: int | None,
) -> None:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        return

    tx = db.get(MeetingTranscript, meeting_id)
    if tx is None:
        tx = MeetingTranscript(meeting_id=meeting_id, status="processing")
        db.add(tx)
    else:
        tx.status = "processing"
        tx.error_message = None
    tx.pipeline_version = PIPELINE_VERSION
    tx.pipeline_stage = "queued"
    db.commit()

    try:
        _run_pipeline(db, meeting, tx, conducted_at, final_elapsed_seconds)
    except Exception as exc:
        log.exception("Transcript pipeline failed meeting=%s", meeting_id)
        tx.status = "failed"
        tx.pipeline_stage = "failed"
        tx.error_message = str(exc)[:1000]
        db.commit()


def _run_pipeline(
    db: Session,
    meeting: Meeting,
    tx: MeetingTranscript,
    conducted_at: datetime,
    final_elapsed_seconds: int | None,
    *,
    _recording_retry: bool = False,
) -> None:
    _set_stage(db, meeting.id, "loading")

    recs = _wait_for_recordings(db, meeting.id, _GRACE_SEC_AFTER_MEETING_END)
    initial_rec_count = len(recs)

    if not recs:
        tx.status = "completed"
        tx.pipeline_stage = "completed"
        tx.merged_text = ""
        tx.generated_at = datetime.utcnow()
        tx.error_message = "No device recordings uploaded."
        db.commit()
        return

    channels: dict[str, tuple[np.ndarray, int]] = {}
    channel_meta: dict[str, ChannelRecording] = {}
    ref_id = recs[0].id

    for rec in recs:
        path = _resolve_path(rec.file_path)
        if path is None:
            continue
        dur = rec.duration_seconds or probe_duration_sec(path) or 0.0
        audio, sr = load_mono_wav(path)
        if len(audio) == 0:
            continue
        channels[rec.id] = (audio, sr)
        offset = 0.0
        if rec.recording_started_at and meeting.conducted_at and final_elapsed_seconds:
            meeting_start = conducted_at - timedelta(seconds=final_elapsed_seconds)
            offset = max(0.0, (rec.recording_started_at - meeting_start).total_seconds())
        channel_meta[rec.id] = ChannelRecording(
            recording_id=rec.id,
            uploader_user_id=rec.uploader_user_id,
            path=path,
            duration_sec=dur or len(audio) / sr,
            offset_sec=offset,
        )

    if not channels:
        tx.status = "failed"
        tx.pipeline_stage = "failed"
        tx.error_message = "Could not decode any recordings."
        db.commit()
        return

    _set_stage(db, meeting.id, "aligning")
    offsets = align_channels(channels, ref_id)
    for cid, off in offsets.items():
        if cid in channel_meta:
            channel_meta[cid].offset_sec += off

    _set_stage(db, meeting.id, "selecting")
    all_regions = []
    for cid, (audio, sr) in channels.items():
        meta = channel_meta[cid]
        shifted = meta.offset_sec
        regions = energy_vad_regions(
            audio,
            sr,
            channel_id=cid,
            uploader_user_id=meta.uploader_user_id,
        )
        for r in regions:
            r.start_sec += shifted
            r.end_sec += shifted
        all_regions.extend(regions)

    selected = select_best_channels(all_regions)

    participant_ids = {
        p.user_id
        for p in db.scalars(
            select(MeetingParticipant).where(MeetingParticipant.meeting_id == meeting.id)
        ).all()
    }
    users = db.scalars(select(User).where(User.id.in_(participant_ids | {r.uploader_user_id for r in recs}))).all()
    labels = {u.id: u.full_name or u.email for u in users}

    refs: list[SpeakerRef] = []
    speaker_matching = (
        settings.ENABLE_SPEAKER_MATCHING and bool(settings.PYANNOTE_AUTH_TOKEN)
    )
    emb_backend = get_embedding_backend() if speaker_matching else None
    if speaker_matching and emb_backend is not None:
        for u in users:
            vec = deserialize_embedding(u.voice_embedding_json)
            if vec is None and u.has_voice_sample and u.voice_file_path:
                p = _resolve_path(u.voice_file_path)
                if p:
                    vec = emb_backend.embed_enrollment(p)
            if vec is not None:
                refs.append(SpeakerRef(user_id=u.id, full_name=u.full_name, embedding=vec))

    asr_backend = get_asr_backend()

    _set_stage(db, meeting.id, "transcribing")
    drafts = []
    for region in selected:
        meta = channel_meta[region.channel_id]
        draft = asr_backend.transcribe_slice(
            meta.path,
            max(0.0, region.start_sec - meta.offset_sec),
            max(0.1, region.end_sec - meta.offset_sec),
            meta.recording_id,
            meta.uploader_user_id,
        )
        if draft is None:
            continue
        draft.start_sec = region.start_sec
        draft.end_sec = region.end_sec
        draft.source_recording_id = meta.recording_id
        draft.source_uploader_user_id = meta.uploader_user_id

        if speaker_matching and emb_backend is not None and (region.end_sec - region.start_sec) >= settings.SPEAKER_MATCH_MIN_SEGMENT_SEC:
            seg_emb = emb_backend.embed_slice(
                meta.path,
                region.start_sec - meta.offset_sec,
                region.end_sec - meta.offset_sec,
            )
            if seg_emb is not None:
                speaker_id, score, status_name = verify_speaker(refs, seg_emb, meta.uploader_user_id)
                draft.speaker_user_id = speaker_id or meta.uploader_user_id
                draft.match_score = score
                draft.match_status = status_name
            else:
                draft.speaker_user_id = meta.uploader_user_id
        else:
            draft.speaker_user_id = meta.uploader_user_id

        drafts.append(draft)

    _set_stage(db, meeting.id, "assembling")
    assembled = assemble_timeline(drafts)
    merged = format_merged_text(assembled, labels)

    final_rec_count = db.scalar(
        select(func.count())
        .select_from(MeetingDeviceRecording)
        .where(MeetingDeviceRecording.meeting_id == meeting.id)
    ) or 0
    if final_rec_count > initial_rec_count and not _recording_retry:
        log.info(
            "New recordings arrived during processing; retrying meeting=%s (%s -> %s)",
            meeting.id,
            initial_rec_count,
            final_rec_count,
        )
        return _run_pipeline(
            db,
            meeting,
            tx,
            conducted_at,
            final_elapsed_seconds,
            _recording_retry=True,
        )

    _set_stage(db, meeting.id, "summarizing")
    minutes_json: dict | None = None
    minutes_error: str | None = None
    try:
        minutes = generate_minutes(assembled, labels, meeting.title)
        minutes_json = {
            "summary": minutes.summary,
            "decisions": minutes.decisions,
            "action_items": minutes.action_items,
        }
    except Exception as exc:
        log.warning("Minutes generation failed for meeting=%s: %s", meeting.id, exc)
        minutes_error = str(exc)[:500]

    db.execute(delete(MeetingTranscriptSegment).where(MeetingTranscriptSegment.meeting_id == meeting.id))
    for seg in assembled:
        db.add(
            MeetingTranscriptSegment(
                id=new_id(),
                meeting_id=meeting.id,
                uploader_user_id=seg.speaker_user_id,
                source_uploader_user_id=seg.source_uploader_user_id,
                source_recording_id=seg.source_recording_id,
                matched_user_id=seg.speaker_user_id if seg.match_status == "matched" else None,
                match_score=_as_py_float(seg.match_score),
                match_status=seg.match_status,
                start_sec=_as_py_float(seg.start_sec) or 0.0,
                end_sec=_as_py_float(seg.end_sec) or 0.0,
                text=seg.text,
                confidence=_as_py_float(seg.confidence),
                word_timestamps_json=json.dumps(
                    [{"word": w.word, "start": float(w.start), "end": float(w.end)} for w in seg.words]
                )
                if seg.words
                else None,
            )
        )

    tx.status = "completed"
    tx.pipeline_stage = "completed"
    tx.merged_text = merged
    tx.minutes_json = json.dumps(minutes_json) if minutes_json is not None else None
    tx.generated_at = datetime.utcnow()
    tx.error_message = minutes_error
    db.commit()

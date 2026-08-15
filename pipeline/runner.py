from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from config.settings import UPLOAD_DIR, settings
from models.meeting import Meeting
from models.meeting_device_recording import MeetingDeviceRecording
from models.meeting_participant import MeetingParticipant
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from models.user import User
from pipeline import PIPELINE_VERSION
from pipeline.align.text_align import pick_reference, resolve_shared_offsets
from pipeline.asr.backends import get_asr_backend
from pipeline.assemble.timeline import assemble_timeline, format_merged_text
from pipeline.audio_io import load_mono_wav, probe_duration_sec, segment_rms
from pipeline.merge.cross_device import merge_across_devices
from pipeline.minutes.gemini_minutes import generate_minutes
from pipeline.speaker.backends import deserialize_embedding, get_embedding_backend
from pipeline.speaker.verify import SpeakerRef, verify_speaker
from pipeline.types import ChannelRecording, TranscriptSegmentDraft
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

    # Resolve file paths + metadata only. Audio is decoded later, one device at a
    # time, so we never hold every recording's samples in RAM at once.
    channel_meta: dict[str, ChannelRecording] = {}
    ref_id = recs[0].id

    for rec in recs:
        path = _resolve_path(rec.file_path)
        if path is None:
            continue
        channel_meta[rec.id] = ChannelRecording(
            recording_id=rec.id,
            uploader_user_id=rec.uploader_user_id,
            path=path,
            duration_sec=rec.duration_seconds or probe_duration_sec(path) or 0.0,
            offset_sec=0.0,
            recording_started_at=(
                rec.recording_started_at.timestamp() if rec.recording_started_at else None
            ),
        )

    if not channel_meta:
        tx.status = "failed"
        tx.pipeline_stage = "failed"
        tx.error_message = "No recording files could be located."
        db.commit()
        return

    # Identity setup: who is in the meeting, plus any enrolled voice prints.
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

    # Bias the recogniser toward this meeting's own vocabulary (title + names) so
    # proper nouns come out right.
    name_list = ", ".join(sorted({n for n in labels.values() if n}))
    prompt_bits: list[str] = []
    if meeting.title:
        prompt_bits.append(f"Meeting: {meeting.title}.")
    if name_list:
        prompt_bits.append(f"Participants: {name_list}.")
    initial_prompt = " ".join(prompt_bits) or None

    # 1) Transcribe each device's WHOLE recording once, in its own LOCAL time
    #    (context-aware = high accuracy). Load one recording at a time and free it
    #    right after, so peak memory stays ~one recording, not all of them at once.
    _set_stage(db, meeting.id, "transcribing")
    per_device: dict[str, list[TranscriptSegmentDraft]] = {}
    decoded_any = False
    for cid, meta in channel_meta.items():
        try:
            audio, sr = load_mono_wav(meta.path)
        except Exception as exc:
            log.warning("Decode failed for recording=%s: %s", cid, exc)
            per_device[cid] = []
            continue
        if len(audio) == 0:
            per_device[cid] = []
            continue
        decoded_any = True
        if not meta.duration_sec:
            meta.duration_sec = len(audio) / sr
        segs = asr_backend.transcribe_file(
            audio,
            sr,
            recording_id=meta.recording_id,
            uploader_user_id=meta.uploader_user_id,
            initial_prompt=initial_prompt,
        )
        for d in segs:
            d.energy = segment_rms(audio, sr, d.start_sec, d.end_sec)
        per_device[cid] = segs
        del audio  # release this recording's samples before loading the next

    if not decoded_any:
        tx.status = "failed"
        tx.pipeline_stage = "failed"
        tx.error_message = "Could not decode any recordings."
        db.commit()
        return

    # 2) Put every device on ONE timeline. Phones share no clock, so align on the
    #    WORDS they both captured (robust for near-field mics); fall back to device
    #    start-time deltas when there isn't enough shared speech.
    _set_stage(db, meeting.id, "aligning")
    ref_id = pick_reference(per_device) or ref_id
    # local->shared offset per device (shared-word alignment, else start-time delta).
    offsets = resolve_shared_offsets(
        per_device,
        {cid: channel_meta[cid].recording_started_at for cid in per_device},
        ref_id,
    )
    all_drafts: list[TranscriptSegmentDraft] = []
    for cid, segs in per_device.items():
        channel_meta[cid].offset_sec = offsets[cid]  # speaker matching converts back to local time
        off = offsets[cid]
        for d in segs:
            d.start_sec = d.start_sec + off
            d.end_sec = max(d.start_sec, d.end_sec + off)
        all_drafts.extend(segs)

    # 3) Collapse the same words captured by multiple phones into one line, keeping
    #    the nearest/clearest mic — whose owner is almost certainly the speaker.
    drafts = merge_across_devices(all_drafts)

    # Optionally confirm/relabel speakers with enrolled voice prints. Group kept
    # segments by device so each recording is decoded ONCE (not once per segment),
    # and only one recording is held in memory at a time.
    if speaker_matching and emb_backend is not None and refs:
        by_device: dict[str, list[TranscriptSegmentDraft]] = {}
        for d in drafts:
            by_device.setdefault(d.source_recording_id, []).append(d)
        for cid, segs in by_device.items():
            meta = channel_meta.get(cid)
            if meta is None:
                continue
            long_enough = [
                d for d in segs
                if (d.end_sec - d.start_sec) >= settings.SPEAKER_MATCH_MIN_SEGMENT_SEC
            ]
            if not long_enough:
                continue
            try:
                audio, sr = load_mono_wav(meta.path)
            except Exception:
                continue
            for d in long_enough:
                seg_emb = emb_backend.embed_span(
                    audio,
                    sr,
                    max(0.0, d.start_sec - meta.offset_sec),
                    max(0.1, d.end_sec - meta.offset_sec),
                )
                if seg_emb is None:
                    continue
                speaker_id, score, status_name = verify_speaker(refs, seg_emb, d.source_uploader_user_id)
                d.speaker_user_id = speaker_id or d.source_uploader_user_id
                d.match_score = score
                d.match_status = status_name
            del audio

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
                start_sec=max(0.0, _as_py_float(seg.start_sec) or 0.0),
                end_sec=max(0.0, _as_py_float(seg.end_sec) or 0.0),
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

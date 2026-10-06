"""Transcript generation entry point — the real single-device pipeline.

Orchestrates, for one completed meeting:

    load -> diarize -> re-embed clusters & identify contacts -> transcribe ->
    assign words to speakers -> resolve labels -> persist segments + merged text
    -> generate minutes (Gemini)

Design: pyannote-first closed-set speaker IDENTIFICATION. Because every member is
enrolled, each diarized cluster is matched 1:1 to a contact (see ``pipeline.match``).

Graceful degradation: if diarization is unavailable (no HF token / model access),
we fall back to an ASR-only transcript with a single ``Speaker 1`` label rather
than failing. Minutes generation is always non-fatal (skipped without a Gemini
key). Any hard error marks the transcript ``failed`` with a message, never crashes
the worker thread.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from config.settings import UPLOAD_DIR, settings
from models.meeting import Meeting
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from pipeline import PIPELINE_VERSION
from pipeline.assemble import (
    assign_words_to_turns,
    flatten_words,
    format_merged_text,
    group_words_into_segments,
)
from utils.ids import new_id

log = logging.getLogger(__name__)


@dataclass
class _MinutesSeg:
    """Duck-typed segment for gemini_minutes.generate_minutes (.text/.speaker_name)."""

    text: str
    speaker_name: str


def _set_stage(db: Session, tx: MeetingTranscript, stage: str) -> None:
    tx.pipeline_stage = stage
    db.commit()


def _mark_overlaps(turns: list[dict]) -> list[dict]:
    """Flag each turn that temporally overlaps a different-speaker turn."""
    for i, a in enumerate(turns):
        a["is_overlap"] = False
    for i, a in enumerate(turns):
        for j, b in enumerate(turns):
            if i == j or a["speaker_label"] == b["speaker_label"]:
                continue
            if min(a["end"], b["end"]) - max(a["start"], b["start"]) > 0.0:
                a["is_overlap"] = True
                break
    return turns


def _speaker_label_map(labels: list[str]) -> dict[str, str]:
    """Stable 'Speaker N' names in order of first appearance."""
    mapping: dict[str, str] = {}
    n = 0
    for lab in labels:
        if lab not in mapping:
            n += 1
            mapping[lab] = f"Speaker {n}"
    return mapping


def _build_initial_prompt(contacts, meeting_title: str) -> str | None:
    names = []
    for c in contacts:
        nm = (c.spoken_name or c.name or "").strip()
        if nm:
            names.append(nm)
    parts = []
    if meeting_title:
        parts.append(f"Meeting: {meeting_title}.")
    if names:
        parts.append("Participants: " + ", ".join(dict.fromkeys(names)) + ".")
    return " ".join(parts) if parts else None


def generate_meeting_transcript(
    db: Session,
    *,
    meeting_id: str,
    conducted_at: datetime,
    final_elapsed_seconds: int | None,
) -> None:
    """Populate/refresh the MeetingTranscript (+ segments + minutes) for a meeting."""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        log.warning("Transcript requested for missing meeting=%s", meeting_id)
        return

    tx = db.get(MeetingTranscript, meeting_id)
    if tx is None:
        tx = MeetingTranscript(meeting_id=meeting_id)
        db.add(tx)
    tx.pipeline_version = PIPELINE_VERSION
    tx.status = "processing"
    tx.pipeline_stage = "queued"
    tx.error_message = None
    tx.minutes_json = None
    tx.merged_text = None
    db.commit()

    # Clear any previous segments (regenerate is idempotent).
    db.execute(delete(MeetingTranscriptSegment).where(MeetingTranscriptSegment.meeting_id == meeting_id))
    db.commit()

    try:
        _run_pipeline(db, meeting, tx)
    except Exception as exc:  # noqa: BLE001 — pipeline must never crash the worker
        log.exception("Transcript pipeline failed for meeting=%s", meeting_id)
        tx.status = "failed"
        tx.pipeline_stage = "failed"
        tx.error_message = f"{type(exc).__name__}: {exc}"[:1000]
        db.commit()


def _run_pipeline(db: Session, meeting: Meeting, tx: MeetingTranscript) -> None:
    from pipeline.audio_io import load_mono_wav

    # --- Load ---------------------------------------------------------------
    _set_stage(db, tx, "loading")
    recording = meeting.recording
    if recording is None or not recording.file_path:
        raise RuntimeError("Meeting has no recording to transcribe.")
    audio_path = UPLOAD_DIR / recording.file_path
    if not audio_path.is_file():
        raise RuntimeError(f"Recording file is missing: {recording.file_path}")

    contacts = list(meeting.contacts)
    audio, sr = load_mono_wav(audio_path)
    if audio.size == 0:
        raise RuntimeError("Recording decoded to empty audio.")

    # Enrolled voiceprints (512-dim) for identification.
    contact_vectors = _load_contact_vectors(contacts)

    # --- Diarize ------------------------------------------------------------
    _set_stage(db, tx, "diarizing")
    from pipeline.diarize import diarize

    turns = diarize(
        audio_path,
        num_speakers=len(contacts) if contacts else None,
        waveform=audio,
        sample_rate=sr,
    )

    initial_prompt = _build_initial_prompt(contacts, meeting.title)

    if turns is None:
        # Graceful degradation: no diarization -> ASR-only, single speaker.
        log.warning("Diarization unavailable for meeting=%s — ASR-only transcript.", meeting.id)
        _run_asr_only(db, meeting, tx, audio, initial_prompt)
        return

    turns = _mark_overlaps(turns)

    # --- Identify speakers --------------------------------------------------
    _set_stage(db, tx, "matching")
    try:
        cluster_assignment = _match_speakers(audio, sr, turns, contact_vectors)
    except Exception:
        # Embedding/matching failure must not sink an otherwise-good diarized
        # transcript — label every cluster unknown and keep going.
        log.exception("Speaker matching failed for meeting=%s — labelling all unknown.", meeting.id)
        cluster_assignment = {
            lab: {"contact_id": None, "score": None, "status": "unknown", "candidates": []}
            for lab in {t["speaker_label"] for t in turns}
        }

    # --- Transcribe ---------------------------------------------------------
    _set_stage(db, tx, "transcribing")
    from pipeline.transcribe import transcribe_file

    asr_segments = transcribe_file(audio, initial_prompt=initial_prompt)

    # --- Assemble -----------------------------------------------------------
    _set_stage(db, tx, "assembling")
    words = assign_words_to_turns(flatten_words(asr_segments), turns)
    grouped = group_words_into_segments(words)

    contacts_by_id = {c.id: c for c in contacts}
    label_fallback = _speaker_label_map([t["speaker_label"] for t in turns])

    persisted = _persist_segments(
        db, meeting, grouped, cluster_assignment, contacts_by_id, label_fallback
    )

    tx.merged_text = format_merged_text(persisted)
    db.commit()

    # --- Minutes ------------------------------------------------------------
    _generate_minutes(db, meeting, tx, persisted)

    tx.status = "completed"
    tx.pipeline_stage = "completed"
    tx.generated_at = datetime.now()
    db.commit()
    log.info("Transcript completed for meeting=%s (%d segments)", meeting.id, len(persisted))


def _run_asr_only(
    db: Session,
    meeting: Meeting,
    tx: MeetingTranscript,
    audio,
    initial_prompt: str | None,
) -> None:
    """Fallback path when diarization is unavailable: transcribe, label Speaker 1."""
    _set_stage(db, tx, "transcribing")
    from pipeline.transcribe import transcribe_file

    asr_segments = transcribe_file(audio, initial_prompt=initial_prompt)

    _set_stage(db, tx, "assembling")
    words = assign_words_to_turns(flatten_words(asr_segments), [])  # no turns
    grouped = group_words_into_segments(words)

    persisted: list[dict] = []
    for seg in grouped:
        if not seg["text"].strip():
            continue
        row = MeetingTranscriptSegment(
            id=new_id(),
            meeting_id=meeting.id,
            matched_contact_id=None,
            label_name="Speaker 1",
            name_source="fallback",
            match_status="unknown",
            match_score=None,
            candidate_contact_ids=None,
            is_overlap=False,
            start_sec=seg["start"],
            end_sec=seg["end"],
            text=seg["text"],
            confidence=seg["confidence"],
            word_timestamps_json=_dump_words(seg["words"]),
        )
        db.add(row)
        persisted.append({"start": seg["start"], "label_name": "Speaker 1", "text": seg["text"]})
    db.commit()

    tx.merged_text = format_merged_text(persisted)
    db.commit()

    _generate_minutes(db, meeting, tx, persisted)

    tx.status = "completed"
    tx.pipeline_stage = "completed"
    tx.generated_at = datetime.now()
    db.commit()
    log.info("ASR-only transcript completed for meeting=%s (%d segments)", meeting.id, len(persisted))


def _load_contact_vectors(contacts) -> dict[str, "object"]:
    from pipeline.speaker.backends import EMBEDDING_DIM, deserialize_embedding

    vectors: dict[str, object] = {}
    for c in contacts:
        vec = deserialize_embedding(c.voice_embedding_json)
        if vec is not None and vec.shape[0] == EMBEDDING_DIM:
            vectors[c.id] = vec
    log.info("Loaded %d enrolled voiceprint(s) of %d contact(s).", len(vectors), len(contacts))
    return vectors


def _match_speakers(audio, sr, turns, contact_vectors) -> dict[str, dict]:
    from pipeline.match import build_cluster_vectors, match_clusters
    from pipeline.speaker.backends import get_embedding_backend

    if not contact_vectors:
        # No enrolled voiceprints -> everyone unknown, but we still diarize.
        labels = {t["speaker_label"] for t in turns}
        return {lab: {"contact_id": None, "score": None, "status": "unknown", "candidates": []} for lab in labels}

    backend = get_embedding_backend()
    cluster_vectors = build_cluster_vectors(audio, sr, turns, backend)
    return match_clusters(cluster_vectors, contact_vectors)


def _persist_segments(
    db: Session,
    meeting: Meeting,
    grouped: list[dict],
    cluster_assignment: dict[str, dict],
    contacts_by_id: dict,
    label_fallback: dict[str, str],
) -> list[dict]:
    persisted: list[dict] = []
    for seg in grouped:
        text = seg["text"].strip()
        if not text:
            continue
        label = seg["speaker_label"]
        assignment = cluster_assignment.get(label, {}) if label is not None else {}
        contact_id = assignment.get("contact_id")
        score = assignment.get("score")
        candidates = assignment.get("candidates") or []

        if contact_id and contact_id in contacts_by_id:
            contact = contacts_by_id[contact_id]
            if contact.spoken_name:
                label_name, name_source = contact.spoken_name, "spoken"
            else:
                label_name, name_source = contact.name, "fallback"
            match_status = "matched"
        else:
            label_name = label_fallback.get(label, "Speaker 1")
            name_source = "fallback"
            match_status = "unknown"
            contact_id = None

        row = MeetingTranscriptSegment(
            id=new_id(),
            meeting_id=meeting.id,
            matched_contact_id=contact_id,
            label_name=label_name,
            name_source=name_source,
            match_status=match_status,
            match_score=score,
            candidate_contact_ids=(json.dumps(candidates) if candidates else None),
            is_overlap=bool(seg["is_overlap"]),
            start_sec=seg["start"],
            end_sec=seg["end"],
            text=text,
            confidence=seg["confidence"],
            word_timestamps_json=_dump_words(seg["words"]),
        )
        db.add(row)
        persisted.append({"start": seg["start"], "label_name": label_name, "text": text})
    db.commit()
    return persisted


def _dump_words(words: list[dict]) -> str | None:
    if not words:
        return None
    slim = [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in words]
    return json.dumps(slim)


def _generate_minutes(db: Session, meeting: Meeting, tx: MeetingTranscript, persisted: list[dict]) -> None:
    """Non-fatal structured minutes via Gemini; skipped without a key."""
    if not persisted:
        return
    tx.pipeline_stage = "minutes"
    db.commit()
    if not settings.GEMINI_API_KEY:
        log.info("GEMINI_API_KEY not set — skipping minutes for meeting=%s.", meeting.id)
        return
    try:
        from pipeline.minutes.gemini_minutes import generate_minutes

        segs = [_MinutesSeg(text=p["text"], speaker_name=p["label_name"]) for p in persisted]
        draft = generate_minutes(segs, meeting.title)
        tx.minutes_json = json.dumps(dataclasses.asdict(draft))
        db.commit()
    except Exception:
        log.exception("Minutes generation failed for meeting=%s (non-fatal).", meeting.id)

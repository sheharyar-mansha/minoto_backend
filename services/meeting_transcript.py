from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from config.settings import UPLOAD_DIR, settings
from models.meeting_device_recording import MeetingDeviceRecording
from models.meeting_member_link import MeetingMemberLink
from models.member import Member
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from models.user import User
from services.speaker_matching import (
    build_reference_embeddings,
    decide_match,
    dedupe_segment_indexes,
    embedding_for_audio_slice,
    rank_candidates,
)
from utils.ids import new_id

_WHISPER_MODEL = None

log = logging.getLogger(__name__)


@dataclass
class _SegmentDraft:
    uploader_user_id: str
    source_audio_path: Path
    source_seg_start_sec: float
    source_seg_end_sec: float
    start_sec: float
    end_sec: float
    text: str
    confidence: float | None
    matched_user_id: str | None = None
    match_score: float | None = None
    match_status: str = "matched"


def _get_model():
    global _WHISPER_MODEL
    from faster_whisper import WhisperModel

    if _WHISPER_MODEL is None:
        _WHISPER_MODEL = WhisperModel(
            settings.TRANSCRIBE_MODEL_SIZE,
            device=settings.TRANSCRIBE_DEVICE,
            compute_type=settings.TRANSCRIBE_COMPUTE_TYPE,
        )
    return _WHISPER_MODEL


def _safe_avg_log_prob(seg: object) -> float | None:
    val = getattr(seg, "avg_logprob", None)
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _transcribe_file(
    abs_path: Path,
    *,
    vad_filter: bool = True,
) -> list[tuple[float, float, str, float | None]]:
    model = _get_model()
    segments, _ = model.transcribe(str(abs_path), vad_filter=vad_filter)
    out: list[tuple[float, float, str, float | None]] = []
    for seg in segments:
        text = str(getattr(seg, "text", "")).strip()
        if not text:
            continue
        start = float(getattr(seg, "start", 0.0))
        end = float(getattr(seg, "end", start))
        if end < start:
            end = start
        out.append((start, end, text, _safe_avg_log_prob(seg)))
    return out


def _meeting_start_time(conducted_at: datetime, final_elapsed_seconds: int | None) -> datetime:
    elapsed = max(0, int(final_elapsed_seconds or 0))
    return conducted_at - timedelta(seconds=elapsed)


def _rostered_participant_count(db: Session, meeting_id: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(MeetingMemberLink)
            .where(MeetingMemberLink.meeting_id == meeting_id)
        )
        or 0
    )


def _device_recording_count(db: Session, meeting_id: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(MeetingDeviceRecording)
            .where(MeetingDeviceRecording.meeting_id == meeting_id)
        )
        or 0
    )


def _wait_for_member_uploads(db: Session, meeting_id: str) -> None:
    """
    Background transcript used to run while the HTTP request was still open, giving
    devices time to upload. Now it starts immediately after complete_meeting commits,
    so we briefly wait for the first MeetingDeviceRecording when the meeting has
    a roster (otherwise we often transcribe an empty list).
    """
    if _rostered_participant_count(db, meeting_id) == 0:
        return
    deadline = time.monotonic() + 55.0
    while time.monotonic() < deadline:
        if _device_recording_count(db, meeting_id) > 0:
            time.sleep(12.0)
            return
        time.sleep(1.5)
        db.expire_all()


def generate_meeting_transcript(
    db: Session,
    *,
    meeting_id: str,
    conducted_at: datetime,
    final_elapsed_seconds: int | None,
) -> None:
    row = db.get(MeetingTranscript, meeting_id)
    if row is None:
        row = MeetingTranscript(meeting_id=meeting_id, status="processing")
        db.add(row)
    else:
        row.status = "processing"
        row.error_message = None
    db.commit()

    try:
        _wait_for_member_uploads(db, meeting_id)
        db.expire_all()
        meeting_start = _meeting_start_time(conducted_at, final_elapsed_seconds)

        def load_uploads() -> list[MeetingDeviceRecording]:
            return list(
                db.scalars(
                    select(MeetingDeviceRecording)
                    .where(MeetingDeviceRecording.meeting_id == meeting_id)
                    .order_by(MeetingDeviceRecording.created_at.asc())
                ).all()
            )

        def build_drafts(
            recs: list[MeetingDeviceRecording],
            *,
            vad_filter: bool,
        ) -> list[_SegmentDraft]:
            out: list[_SegmentDraft] = []
            for rec in recs:
                abs_path = UPLOAD_DIR / rec.file_path
                if not abs_path.exists():
                    log.warning(
                        "transcript missing file meeting=%s recording=%s path=%s",
                        meeting_id,
                        rec.id,
                        abs_path,
                    )
                    continue
                recording_end_abs = max(
                    0.0,
                    float((rec.created_at - meeting_start).total_seconds()),
                )
                estimated_duration = float(rec.duration_seconds or 0)
                base_start_abs = max(0.0, recording_end_abs - estimated_duration)
                for seg_start, seg_end, text, conf in _transcribe_file(
                    abs_path,
                    vad_filter=vad_filter,
                ):
                    start_abs = max(0.0, base_start_abs + seg_start)
                    end_abs = max(start_abs, base_start_abs + seg_end)
                    out.append(
                        _SegmentDraft(
                            uploader_user_id=rec.uploader_user_id,
                            source_audio_path=abs_path,
                            source_seg_start_sec=seg_start,
                            source_seg_end_sec=seg_end,
                            start_sec=start_abs,
                            end_sec=end_abs,
                            text=text,
                            confidence=conf,
                            matched_user_id=rec.uploader_user_id,
                            match_status="matched",
                        )
                    )
            out.sort(key=lambda s: (s.start_sec, s.uploader_user_id, s.end_sec))
            return out

        uploads = load_uploads()
        drafts = build_drafts(uploads, vad_filter=True)
        if not drafts and uploads:
            db.expire_all()
            uploads = load_uploads()
            drafts = build_drafts(uploads, vad_filter=True)
        if not drafts and uploads:
            log.info(
                "transcript retry without VAD meeting=%s recordings=%d",
                meeting_id,
                len(uploads),
            )
            drafts = build_drafts(uploads, vad_filter=False)

        uploader_ids = list({r.uploader_user_id for r in uploads})
        users = {}
        if uploader_ids:
            users = {
                u.id: u.full_name
                for u in db.scalars(select(User).where(User.id.in_(uploader_ids))).all()
            }
        log.info(
            "transcript pass meeting=%s uploads=%d drafts=%d",
            meeting_id,
            len(uploads),
            len(drafts),
        )

        if settings.ENABLE_SPEAKER_MATCHING:
            try:
                participant_refs = _participant_voice_reference_paths(db, meeting_id)
                refs = build_reference_embeddings(participant_refs)
                for d in drafts:
                    seg_embed = embedding_for_audio_slice(
                        d.source_audio_path, d.source_seg_start_sec, d.source_seg_end_sec
                    )
                    candidates = rank_candidates(seg_embed, refs)
                    decision = decide_match(candidates)
                    d.matched_user_id = decision.matched_user_id
                    d.match_score = decision.match_score
                    d.match_status = decision.match_status
            except Exception:
                # Fail open: preserve Phase 1 behavior and avoid blocking transcript generation.
                for d in drafts:
                    d.matched_user_id = d.uploader_user_id
                    d.match_score = None
                    d.match_status = "matched"

        keep_ix = dedupe_segment_indexes(
            (
                d.start_sec,
                d.end_sec,
                d.text,
                d.matched_user_id or "unknown",
                d.match_score,
            )
            for d in drafts
        )
        drafts = [d for idx, d in enumerate(drafts) if idx in keep_ix]

        db.execute(
            delete(MeetingTranscriptSegment).where(MeetingTranscriptSegment.meeting_id == meeting_id)
        )
        merged_lines: list[str] = []
        for s in drafts:
            speaker_user_id = s.matched_user_id or s.uploader_user_id
            speaker_name = users.get(speaker_user_id, "Unknown")
            if s.match_status == "unknown":
                speaker_name = "Unknown"
            db.add(
                MeetingTranscriptSegment(
                    id=new_id(),
                    meeting_id=meeting_id,
                    uploader_user_id=s.uploader_user_id,
                    source_uploader_user_id=s.uploader_user_id,
                    matched_user_id=s.matched_user_id,
                    match_score=s.match_score,
                    match_status=s.match_status,
                    start_sec=s.start_sec,
                    end_sec=s.end_sec,
                    text=s.text,
                    confidence=s.confidence,
                )
            )
            mm = int(s.start_sec // 60)
            ss = int(s.start_sec % 60)
            merged_lines.append(f"[{mm:02d}:{ss:02d}] {speaker_name}: {s.text}")

        final_row = db.get(MeetingTranscript, meeting_id)
        assert final_row is not None
        final_row.status = "completed"
        final_row.generated_at = datetime.now()
        final_row.merged_text = "\n".join(merged_lines) if merged_lines else ""
        final_row.error_message = None
        db.add(final_row)
        db.commit()
    except Exception as exc:
        failed = db.get(MeetingTranscript, meeting_id)
        if failed is None:
            failed = MeetingTranscript(meeting_id=meeting_id)
        failed.status = "failed"
        failed.error_message = str(exc)[:1000]
        failed.generated_at = datetime.now()
        db.add(failed)
        db.commit()


def _participant_voice_reference_paths(db: Session, meeting_id: str) -> dict[str, Path]:
    links = db.scalars(
        select(MeetingMemberLink)
        .where(MeetingMemberLink.meeting_id == meeting_id)
        .join(Member, Member.id == MeetingMemberLink.member_id)
    ).all()
    member_emails = []
    for link in links:
        if link.member is not None and link.member.email:
            member_emails.append(link.member.email.strip().lower())
    if not member_emails:
        return {}
    users = db.scalars(
        select(User).where(User.email.in_(member_emails), User.has_voice_sample.is_(True))
    ).all()
    out: dict[str, Path] = {}
    for u in users:
        if u.voice_file_path:
            out[u.id] = UPLOAD_DIR / u.voice_file_path
    return out

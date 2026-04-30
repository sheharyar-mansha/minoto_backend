from __future__ import annotations

import json
import logging
import re
import subprocess
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
    SpeakerMatchCandidate,
    SpeakerMatchResult,
    build_reference_embeddings,
    decide_match,
    dedupe_segment_indexes,
    embedding_for_audio_slice,
    rank_candidates,
)
from utils.ids import new_id

_WHISPER_MODEL = None

log = logging.getLogger(__name__)

# Upload / encoding happens after capture; without capping, we treat file end as
# rec.created_at which is too late on the meeting timeline and shifts timestamps ahead.
_GRACE_SEC_AFTER_MEETING_END = 20.0


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def _normalize_text_key(text: str) -> str:
    return " ".join(re.findall(r"\w+", (text or "").lower()))


def _resolve_upload_relative_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    p = Path(raw)
    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(UPLOAD_DIR / p)
        s = str(p).replace("\\", "/").lstrip("/")
        if s.lower().startswith("uploads/"):
            candidates.append(UPLOAD_DIR / s.split("/", 1)[1])
    for c in candidates:
        if c.exists():
            return c
    return candidates[0] if candidates else None


def _resolve_cross_device_speaker_conflicts(drafts: list["_SegmentDraft"]) -> None:
    """
    If near-same utterance appears from multiple uploaders with conflicting matched users,
    mark all as outsider to avoid confidently wrong attribution.
    """
    n = len(drafts)
    for i in range(n):
        di = drafts[i]
        key_i = _normalize_text_key(di.text)
        if not key_i:
            continue
        group = [i]
        speakers = {di.matched_user_id} if di.match_status == "matched" and di.matched_user_id else set()
        uploaders = {di.uploader_user_id}
        for j in range(i + 1, n):
            dj = drafts[j]
            if abs(di.start_sec - dj.start_sec) > settings.SPEAKER_DEDUPE_MAX_GAP_SEC:
                continue
            if _normalize_text_key(dj.text) != key_i:
                continue
            group.append(j)
            uploaders.add(dj.uploader_user_id)
            if dj.match_status == "matched" and dj.matched_user_id:
                speakers.add(dj.matched_user_id)
        if len(group) >= 2 and len(uploaders) >= 2 and len(speakers) >= 2:
            for idx in group:
                drafts[idx].matched_user_id = None
                drafts[idx].match_status = "outsider"


def _apply_soft_biases(
    candidates: list[SpeakerMatchCandidate],
    *,
    uploader_user_id: str,
    prev_matched_user_id: str | None,
    gap_from_prev_sec: float | None,
) -> list[SpeakerMatchCandidate]:
    adjusted: list[SpeakerMatchCandidate] = []
    for c in candidates:
        bonus = 0.0
        if c.user_id == uploader_user_id:
            bonus += settings.SPEAKER_MATCH_UPLOADER_BONUS
        if (
            prev_matched_user_id
            and c.user_id == prev_matched_user_id
            and gap_from_prev_sec is not None
            and gap_from_prev_sec <= settings.SPEAKER_MATCH_CONTINUITY_WINDOW_SEC
        ):
            bonus += settings.SPEAKER_MATCH_CONTINUITY_BONUS
        adjusted.append(SpeakerMatchCandidate(user_id=c.user_id, score=c.score + bonus))
    adjusted.sort(key=lambda c: c.score, reverse=True)
    return adjusted


def _uploader_borderline_fallback(
    *,
    candidates: list[SpeakerMatchCandidate],
    uploader_user_id: str,
    current: SpeakerMatchResult,
) -> SpeakerMatchResult:
    """
    In multi-device meetings, cross-bleed can make top-vs-uploader scores very close.
    If uploader score is decent and close to top, prefer uploader over outsider or
    weak cross-device matches.
    """
    if not candidates:
        return current
    best = candidates[0]
    uploader = next((c for c in candidates if c.user_id == uploader_user_id), None)
    if uploader is None or uploader.score < settings.SPEAKER_MATCH_UPLOADER_MIN_SCORE:
        return current

    close_to_best = (best.score - uploader.score) <= settings.SPEAKER_MATCH_UPLOADER_STEAL_MARGIN
    if not close_to_best:
        return current

    # Keep existing confident uploader decisions as-is.
    if current.match_status == "matched" and current.matched_user_id == uploader_user_id:
        return current

    return SpeakerMatchResult(
        matched_user_id=uploader_user_id,
        match_score=uploader.score,
        match_status="matched",
    )


def _debug_speaker_matching(
    *,
    meeting_id: str,
    draft: "_SegmentDraft",
    refs_count: int,
    candidates: list[SpeakerMatchCandidate],
    decision_user_id: str | None,
    decision_status: str,
    reason: str,
) -> None:
    if not settings.DEBUG_SPEAKER_MATCHING:
        return
    best = candidates[0] if len(candidates) > 0 else None
    second = candidates[1] if len(candidates) > 1 else None
    margin = None
    if best is not None:
        margin = best.score - (second.score if second is not None else -1.0)
    log.warning(
        (
            "speaker_match meeting=%s uploader=%s start=%.2f end=%.2f refs=%d "
            "best=%s:%.4f second=%s:%.4f margin=%s selected=%s status=%s reason=%s text=%r"
        ),
        meeting_id,
        draft.uploader_user_id,
        draft.start_sec,
        draft.end_sec,
        refs_count,
        best.user_id if best else None,
        best.score if best else -1.0,
        second.user_id if second else None,
        second.score if second else -1.0,
        f"{margin:.4f}" if margin is not None else None,
        decision_user_id,
        decision_status,
        reason,
        (draft.text or "")[:90],
    )


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


def _ffprobe_duration_seconds(path: Path) -> float | None:
    """Best-effort media duration (seconds); used when duration_seconds was not sent."""
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        dur = json.loads(proc.stdout).get("format", {}).get("duration")
        if dur is None:
            return None
        return max(0.0, float(dur))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _recording_end_abs_seconds(
    *,
    rec_created_at: datetime,
    meeting_start: datetime,
    final_elapsed_seconds: int | None,
) -> float:
    """Seconds from meeting_start to when the recording should align on the meeting timeline."""
    raw = max(0.0, float((rec_created_at - meeting_start).total_seconds()))
    if final_elapsed_seconds is None:
        return raw
    meeting_end = max(0.0, float(final_elapsed_seconds))
    return min(raw, meeting_end + _GRACE_SEC_AFTER_MEETING_END)


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
                fixed = _resolve_upload_relative_path(rec.file_path)
                if fixed is not None:
                    abs_path = fixed
                if not abs_path.exists():
                    log.warning(
                        "transcript missing file meeting=%s recording=%s path=%s",
                        meeting_id,
                        rec.id,
                        abs_path,
                    )
                    continue
                recording_end_abs = _recording_end_abs_seconds(
                    rec_created_at=rec.created_at,
                    meeting_start=meeting_start,
                    final_elapsed_seconds=final_elapsed_seconds,
                )
                estimated_duration = float(rec.duration_seconds or 0)
                if estimated_duration <= 0:
                    probed = _ffprobe_duration_seconds(abs_path)
                    if probed is not None and probed > 0:
                        estimated_duration = probed
                    else:
                        log.warning(
                            "transcript zero_duration meeting=%s recording=%s path=%s",
                            meeting_id,
                            rec.id,
                            abs_path,
                        )
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
                uploader_refs = _uploader_voice_reference_paths(
                    db, [r.uploader_user_id for r in uploads]
                )
                # Union both sources; uploader refs rescue cases where Member.email does not
                # map cleanly to User.email but uploaders already have valid voice samples.
                participant_refs.update(uploader_refs)
                refs = build_reference_embeddings(participant_refs)
                if settings.DEBUG_SPEAKER_MATCHING:
                    log.warning(
                        "speaker_match_setup meeting=%s embeddings=%d ref_paths=%d",
                        meeting_id,
                        len(refs),
                        len(participant_refs),
                    )
                prev_matched_user_id: str | None = None
                prev_start_sec: float | None = None
                for d in drafts:
                    seg_duration = max(0.0, d.source_seg_end_sec - d.source_seg_start_sec)
                    if seg_duration < settings.SPEAKER_MATCH_MIN_SEGMENT_SEC or not refs:
                        d.matched_user_id = None
                        d.match_score = None
                        d.match_status = "outsider"
                        _debug_speaker_matching(
                            meeting_id=meeting_id,
                            draft=d,
                            refs_count=len(refs),
                            candidates=[],
                            decision_user_id=None,
                            decision_status=d.match_status,
                            reason="segment_too_short_or_no_refs",
                        )
                        continue
                    seg_embed = embedding_for_audio_slice(
                        d.source_audio_path, d.source_seg_start_sec, d.source_seg_end_sec
                    )
                    candidates = rank_candidates(seg_embed, refs)
                    gap = None if prev_start_sec is None else max(0.0, d.start_sec - prev_start_sec)
                    candidates = _apply_soft_biases(
                        candidates,
                        uploader_user_id=d.uploader_user_id,
                        prev_matched_user_id=prev_matched_user_id,
                        gap_from_prev_sec=gap,
                    )
                    decision = decide_match(candidates)
                    decision = _uploader_borderline_fallback(
                        candidates=candidates,
                        uploader_user_id=d.uploader_user_id,
                        current=decision,
                    )
                    wc = _word_count(d.text)
                    if wc < settings.SPEAKER_MATCH_MIN_WORDS:
                        best = candidates[0] if candidates else None
                        second = candidates[1] if len(candidates) > 1 else None
                        margin = (best.score - second.score) if (best and second) else (
                            best.score + 1.0 if best else -1.0
                        )
                        short_floor = (
                            settings.SPEAKER_MATCH_MIN_SCORE_SINGLE_REF
                            if len(refs) == 1
                            else settings.SPEAKER_MATCH_SHORT_UTTERANCE_MIN_SCORE
                        )
                        if (
                            best is None
                            or best.score < short_floor
                            or margin < (settings.SPEAKER_MATCH_MARGIN + 0.02)
                        ):
                            d.matched_user_id = None
                            d.match_score = best.score if best else None
                            d.match_status = "outsider"
                            _debug_speaker_matching(
                                meeting_id=meeting_id,
                                draft=d,
                                refs_count=len(refs),
                                candidates=candidates,
                                decision_user_id=None,
                                decision_status=d.match_status,
                                reason="short_utterance_low_confidence",
                            )
                            continue
                    d.matched_user_id = decision.matched_user_id
                    d.match_score = decision.match_score
                    d.match_status = decision.match_status
                    _debug_speaker_matching(
                        meeting_id=meeting_id,
                        draft=d,
                        refs_count=len(refs),
                        candidates=candidates,
                        decision_user_id=d.matched_user_id,
                        decision_status=d.match_status,
                        reason="model_decision",
                    )
                    if d.match_status == "matched" and d.matched_user_id:
                        prev_matched_user_id = d.matched_user_id
                        prev_start_sec = d.start_sec
                _resolve_cross_device_speaker_conflicts(drafts)
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
                d.matched_user_id or "outsider",
                d.match_score,
                d.confidence,
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
            speaker_name = users.get(speaker_user_id, "Outsider")
            if s.match_status in {"unknown", "outsider"}:
                speaker_name = "Outsider"
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
        resolved = _resolve_upload_relative_path(u.voice_file_path)
        if resolved and resolved.exists():
            out[u.id] = resolved
        elif settings.DEBUG_SPEAKER_MATCHING:
            log.warning(
                "speaker_ref_missing meeting=%s user=%s raw_path=%r",
                meeting_id,
                u.id,
                u.voice_file_path,
            )
    return out


def _uploader_voice_reference_paths(db: Session, uploader_ids: list[str]) -> dict[str, Path]:
    ids = [u for u in set(uploader_ids) if u]
    if not ids:
        return {}
    users = db.scalars(
        select(User).where(User.id.in_(ids), User.has_voice_sample.is_(True))
    ).all()
    out: dict[str, Path] = {}
    for u in users:
        resolved = _resolve_upload_relative_path(u.voice_file_path)
        if resolved and resolved.exists():
            out[u.id] = resolved
        elif settings.DEBUG_SPEAKER_MATCHING:
            log.warning(
                "speaker_uploader_ref_missing user=%s raw_path=%r",
                u.id,
                u.voice_file_path,
            )
    return out

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from config.settings import settings

_EMBED_MODEL = None


@dataclass
class SpeakerMatchCandidate:
    user_id: str
    score: float


@dataclass
class SpeakerMatchResult:
    matched_user_id: str | None
    match_score: float | None
    match_status: str


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom <= 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _get_embed_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is not None:
        return _EMBED_MODEL
    from pyannote.audio import Model
    from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding

    model = Model.from_pretrained(
        settings.PYANNOTE_EMBEDDING_MODEL,
        use_auth_token=settings.PYANNOTE_AUTH_TOKEN or None,
    )
    _EMBED_MODEL = PretrainedSpeakerEmbedding(model)
    return _EMBED_MODEL


def _segment_wav_slice(src_audio: Path, start_sec: float, end_sec: float) -> Path:
    fd, tmp_name = tempfile.mkstemp(suffix=".wav")
    Path(tmp_name).unlink(missing_ok=True)
    out_path = Path(tmp_name)
    duration = max(0.2, end_sec - start_sec)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{max(0.0, start_sec):.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(src_audio),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def embedding_for_audio_file(path: Path) -> np.ndarray:
    model = _get_embed_model()
    vec = model(str(path))
    arr = np.asarray(vec).reshape(-1).astype(np.float32)
    return arr


def embedding_for_audio_slice(path: Path, start_sec: float, end_sec: float) -> np.ndarray:
    tmp = _segment_wav_slice(path, start_sec, end_sec)
    try:
        return embedding_for_audio_file(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def build_reference_embeddings(paths_by_user: dict[str, Path]) -> dict[str, np.ndarray]:
    refs: dict[str, np.ndarray] = {}
    for user_id, sample_path in paths_by_user.items():
        if not sample_path.exists():
            continue
        try:
            refs[user_id] = embedding_for_audio_file(sample_path)
        except Exception:
            continue
    return refs


def rank_candidates(
    segment_embedding: np.ndarray,
    refs: dict[str, np.ndarray],
) -> list[SpeakerMatchCandidate]:
    out = [
        SpeakerMatchCandidate(user_id=user_id, score=_cosine_similarity(segment_embedding, ref_vec))
        for user_id, ref_vec in refs.items()
    ]
    out.sort(key=lambda c: c.score, reverse=True)
    return out


def decide_match(candidates: Sequence[SpeakerMatchCandidate]) -> SpeakerMatchResult:
    if not candidates:
        return SpeakerMatchResult(matched_user_id=None, match_score=None, match_status="unknown")
    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    margin = best.score - (second.score if second else -1.0)
    if best.score < settings.SPEAKER_MATCH_MIN_SCORE or margin < settings.SPEAKER_MATCH_MARGIN:
        return SpeakerMatchResult(matched_user_id=None, match_score=best.score, match_status="unknown")
    return SpeakerMatchResult(
        matched_user_id=best.user_id,
        match_score=best.score,
        match_status="matched",
    )


def text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def dedupe_segment_indexes(
    rows: Iterable[tuple[float, float, str, str, float | None]],
) -> set[int]:
    """
    Input tuple per row: (start_sec, end_sec, text, speaker_key, match_score).
    Returns indexes to keep.
    """
    arr = list(rows)
    keep = set(range(len(arr)))
    for i in range(len(arr)):
        if i not in keep:
            continue
        si, ei, ti, spi, ci = arr[i]
        for j in range(i + 1, len(arr)):
            if j not in keep:
                continue
            sj, ej, tj, spj, cj = arr[j]
            if abs(si - sj) > settings.SPEAKER_MATCH_MAX_GAP_SEC:
                continue
            if spi != spj:
                continue
            if text_similarity(ti, tj) < settings.SPEAKER_MATCH_TEXT_SIMILARITY:
                continue
            score_i = ci if ci is not None else -1.0
            score_j = cj if cj is not None else -1.0
            if score_i > score_j or (score_i == score_j and len(ti) >= len(tj)):
                keep.discard(j)
            else:
                keep.discard(i)
                break
    return keep

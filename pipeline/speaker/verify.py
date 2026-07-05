from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from config.settings import settings
from pipeline.speaker.backends import normalize_embedding_vector
from pipeline.audio_io import load_mono_wav, slice_audio


@dataclass
class SpeakerRef:
    user_id: str
    full_name: str
    embedding: np.ndarray


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = normalize_embedding_vector(a)
    b = normalize_embedding_vector(b)
    if a is None or b is None:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def embed_audio(path, start_sec: float, end_sec: float) -> np.ndarray | None:
    from pipeline.speaker.backends import get_embedding_backend

    return get_embedding_backend().embed_slice(path, start_sec, end_sec)


def verify_speaker(
    refs: list[SpeakerRef],
    segment_embedding: np.ndarray,
    uploader_user_id: str,
) -> tuple[str | None, float, str]:
    if segment_embedding is None or not refs:
        return uploader_user_id, 0.0, "unknown"
    scores = [(ref, cosine(segment_embedding, ref.embedding)) for ref in refs]
    scores.sort(key=lambda x: x[1], reverse=True)
    best_ref, best_score = scores[0]
    uploader_bonus = settings.SPEAKER_DEVICE_PRIOR_BONUS
    for ref, score in scores:
        if ref.user_id == uploader_user_id:
            if score + uploader_bonus >= best_score:
                best_ref, best_score = ref, score + uploader_bonus
            break
    threshold = settings.SPEAKER_MATCH_MIN_SCORE
    if best_score >= threshold:
        return best_ref.user_id, best_score, "matched"
    if best_ref.user_id == uploader_user_id and best_score >= settings.SPEAKER_MATCH_UPLOADER_MIN_SCORE:
        return uploader_user_id, best_score, "matched"
    return None, best_score, "unknown"

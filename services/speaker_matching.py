from __future__ import annotations

import contextlib
import gc
import logging
import re
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import torch

import hf_hub_compat
import pa_torchaudio_shim

hf_hub_compat.apply_hf_hub_use_auth_token_compat()
pa_torchaudio_shim.apply_pyannote_torchaudio_shim()

from config.settings import settings

_EMBED_MODEL = None
log = logging.getLogger(__name__)


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


def _temp_wav_path_for_ffmpeg() -> Path:
    """Closed, deleted placeholder path so ffmpeg can create the file (Windows-safe)."""
    tf = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    path = Path(tf.name)
    tf.close()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return path


@contextlib.contextmanager
def _pyannote_trusted_checkpoint_torch_load():
    """
    PyTorch 2.6+ treats torch.load(weights_only=None) like True. Lightning's pl_load
    passes weights_only=None for local files, which breaks pyannote checkpoints that
    pickle Lightning objects. Force False when None or omitted (HF-trusted checkpoints).
    """
    orig = torch.load

    def _load(*args, **kwargs):
        if kwargs.get("weights_only") is None:
            kwargs["weights_only"] = False
        return orig(*args, **kwargs)

    torch.load = _load  # type: ignore[method-assign]
    try:
        yield
    finally:
        torch.load = orig  # type: ignore[method-assign]


def _safe_unlink(path: Path) -> None:
    """Windows often keeps WAV files locked briefly after PyTorch/pyannote reads them."""
    for _ in range(25):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError:
            gc.collect()
            time.sleep(0.04)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.warning("temp_audio_not_deleted path=%s", path)


def _get_embed_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is not None:
        return _EMBED_MODEL
    from pyannote.audio import Model
    from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding

    with _pyannote_trusted_checkpoint_torch_load():
        model = Model.from_pretrained(
            settings.PYANNOTE_EMBEDDING_MODEL,
            use_auth_token=settings.PYANNOTE_AUTH_TOKEN or None,
        )
        _EMBED_MODEL = PretrainedSpeakerEmbedding(model)
    return _EMBED_MODEL


def _segment_wav_slice(src_audio: Path, start_sec: float, end_sec: float) -> Path:
    out_path = _temp_wav_path_for_ffmpeg()
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


def _ffmpeg_full_to_wav_16k_mono(src: Path) -> Path:
    """Decode any container (mp4/m4a/webm/…) to mono 16 kHz WAV for pyannote."""
    out_path = _temp_wav_path_for_ffmpeg()
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _load_wav_mono_float_tensor(path_wav: Path, *, expected_sr: int) -> torch.Tensor:
    """
    Read 16-bit PCM WAV into (1, 1, num_samples) float32 tensor.
    Avoids torchaudio/pyannote file I/O (fixes broken torchaudio builds on Windows).
    """
    with wave.open(str(path_wav), "rb") as w:
        sampwidth = w.getsampwidth()
        sr = w.getframerate()
        nch = w.getnchannels()
        if sampwidth != 2:
            raise ValueError(f"expected 16-bit PCM WAV, got sample width {sampwidth}")
        raw = w.readframes(w.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if nch > 1:
        audio = audio.reshape(-1, nch).mean(axis=1)
    if sr != expected_sr:
        log.warning(
            "wav_sample_rate_mismatch got=%s expected=%s path=%s",
            sr,
            expected_sr,
            path_wav,
        )
    t = torch.from_numpy(audio).unsqueeze(0).unsqueeze(0)
    return t


def _embedding_from_wav(path_wav: Path) -> np.ndarray:
    embedder = _get_embed_model()
    sr = int(embedder.sample_rate)
    waveforms = _load_wav_mono_float_tensor(path_wav, expected_sr=sr)
    vec = embedder(waveforms)
    return np.asarray(vec).reshape(-1).astype(np.float32)


def embedding_for_audio_file(path: Path) -> np.ndarray:
    tmp = _ffmpeg_full_to_wav_16k_mono(path)
    try:
        return _embedding_from_wav(tmp)
    finally:
        _safe_unlink(tmp)


def embedding_for_audio_slice(path: Path, start_sec: float, end_sec: float) -> np.ndarray:
    tmp = _segment_wav_slice(path, start_sec, end_sec)
    try:
        return _embedding_from_wav(tmp)
    finally:
        _safe_unlink(tmp)


def build_reference_embeddings(paths_by_user: dict[str, Path]) -> dict[str, np.ndarray]:
    refs: dict[str, np.ndarray] = {}
    for user_id, sample_path in paths_by_user.items():
        if not sample_path.exists():
            log.warning("speaker_ref_skip missing file user=%s path=%s", user_id, sample_path)
            continue
        try:
            refs[user_id] = embedding_for_audio_file(sample_path)
        except Exception as exc:
            log.warning(
                "speaker_ref_embed_failed user=%s path=%s: %s",
                user_id,
                sample_path,
                exc,
            )
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
        return SpeakerMatchResult(matched_user_id=None, match_score=None, match_status="outsider")
    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    min_score = (
        settings.SPEAKER_MATCH_MIN_SCORE_SINGLE_REF
        if second is None
        else settings.SPEAKER_MATCH_MIN_SCORE
    )
    if best.score < min_score:
        return SpeakerMatchResult(matched_user_id=None, match_score=best.score, match_status="outsider")
    # Only one enrolled voice: no second-speaker ambiguity.
    if second is None:
        return SpeakerMatchResult(
            matched_user_id=best.user_id,
            match_score=best.score,
            match_status="matched",
        )
    margin = best.score - second.score
    if margin < settings.SPEAKER_MATCH_MARGIN:
        return SpeakerMatchResult(matched_user_id=None, match_score=best.score, match_status="outsider")
    return SpeakerMatchResult(
        matched_user_id=best.user_id,
        match_score=best.score,
        match_status="matched",
    )


def text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sa = set(re.findall(r"\w+", a.lower()))
    sb = set(re.findall(r"\w+", b.lower()))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def dedupe_segment_indexes(
    rows: Iterable[tuple[float, float, str, str, float | None, float | None]],
) -> set[int]:
    """
    Input tuple per row:
      (start_sec, end_sec, text, speaker_key, match_score, asr_confidence).
    Returns indexes to keep.
    """
    arr = list(rows)
    keep = set(range(len(arr)))
    for i in range(len(arr)):
        if i not in keep:
            continue
        si, ei, ti, spi, ci, ai = arr[i]
        for j in range(i + 1, len(arr)):
            if j not in keep:
                continue
            sj, ej, tj, spj, cj, aj = arr[j]
            if abs(si - sj) > settings.SPEAKER_DEDUPE_MAX_GAP_SEC:
                continue
            if text_similarity(ti, tj) < settings.SPEAKER_MATCH_TEXT_SIMILARITY:
                continue
            # Two devices often capture the same utterance with slight timing drift.
            # Prefer a confidently matched speaker over unknown, then better
            # embedding score, then better ASR confidence / longer text.
            i_is_matched = spi not in {"unknown", "outsider"}
            j_is_matched = spj not in {"unknown", "outsider"}
            score_i = ci if ci is not None else -1.0
            score_j = cj if cj is not None else -1.0
            conf_i = ai if ai is not None else -99.0
            conf_j = aj if aj is not None else -99.0

            if i_is_matched != j_is_matched:
                keep_i = i_is_matched
            elif score_i != score_j:
                keep_i = score_i > score_j
            elif conf_i != conf_j:
                keep_i = conf_i > conf_j
            else:
                keep_i = len(ti) >= len(tj)

            if keep_i:
                keep.discard(j)
            else:
                keep.discard(i)
                break
    return keep

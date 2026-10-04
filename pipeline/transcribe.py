"""Single-file speech-to-text with faster-whisper (CTranslate2).

One cached ``WhisperModel`` is reused across calls. ``transcribe_file`` takes an
already-decoded mono/16k float32 waveform (so we decode each recording once in the
runner) and returns a list of plain dicts — no faster-whisper objects leak out, so
the rest of the pipeline stays decoupled from the ASR library.

Decoding is tuned for meeting audio: VAD gating, word timestamps, a temperature
fallback ladder, and the standard hallucination guards (compression-ratio /
log-prob / no-speech thresholds). Empty and degenerate (single-token-repeat)
segments are dropped.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache

import numpy as np

from config.settings import settings
from pipeline.device import asr_device_compute

log = logging.getLogger(__name__)

__all__ = ["transcribe_file", "get_whisper_model"]

# Temperature fallback ladder: whisper retries a chunk at the next temperature
# when the decode trips the compression-ratio / log-prob guards.
_TEMPERATURE_LADDER = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


@lru_cache(maxsize=1)
def get_whisper_model():
    """Load (once) the faster-whisper model on the resolved device/compute type."""
    from faster_whisper import WhisperModel

    device, compute_type = asr_device_compute()
    log.info(
        "Loading faster-whisper model=%s device=%s compute=%s",
        settings.TRANSCRIBE_MODEL_SIZE,
        device,
        compute_type,
    )
    return WhisperModel(
        settings.TRANSCRIBE_MODEL_SIZE,
        device=device,
        compute_type=compute_type,
    )


def _language() -> str | None:
    lang = (settings.TRANSCRIBE_LANGUAGE or "").strip().lower()
    if not lang or lang == "auto":
        return None
    return lang


def _is_degenerate(text: str) -> bool:
    """True for whisper hallucination artefacts: empty or one token repeated."""
    tokens = text.split()
    if not tokens:
        return True
    # e.g. "you you you you" / "Thank you. Thank you. Thank you." stripped to tokens.
    unique = {t.strip(".,!?;:-").lower() for t in tokens}
    unique.discard("")
    return len(unique) <= 1 and len(tokens) >= 4


def transcribe_file(audio: np.ndarray, initial_prompt: str | None = None) -> list[dict]:
    """Transcribe a decoded waveform.

    Args:
        audio: mono float32 waveform sampled at 16 kHz.
        initial_prompt: optional biasing text (e.g. speaker names + meeting title).

    Returns:
        One dict per kept segment::

            {start, end, text, confidence, avg_logprob, no_speech_prob,
             words: [{word, start, end, probability}]}
    """
    model = get_whisper_model()
    samples = np.ascontiguousarray(np.asarray(audio, dtype=np.float32).reshape(-1))
    if samples.size == 0:
        return []

    segments, _info = model.transcribe(
        samples,
        language=_language(),
        beam_size=settings.TRANSCRIBE_BEAM_SIZE,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
        initial_prompt=(initial_prompt or None),
        temperature=_TEMPERATURE_LADDER,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
    )

    out: list[dict] = []
    for seg in segments:
        text = (seg.text or "").strip()
        if not text or _is_degenerate(text):
            continue

        avg_logprob = float(seg.avg_logprob) if seg.avg_logprob is not None else -10.0
        words = []
        for w in seg.words or []:
            word_text = (w.word or "").strip()
            if not word_text:
                continue
            words.append(
                {
                    "word": word_text,
                    "start": float(w.start),
                    "end": float(w.end),
                    "probability": float(getattr(w, "probability", 0.0) or 0.0),
                }
            )

        out.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": text,
                "avg_logprob": avg_logprob,
                "confidence": float(math.exp(avg_logprob)),
                "no_speech_prob": float(seg.no_speech_prob or 0.0),
                "words": words,
            }
        )
    log.info("Transcribed %d usable segment(s)", len(out))
    return out

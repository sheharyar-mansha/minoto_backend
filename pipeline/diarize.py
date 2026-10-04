"""Speaker diarization with pyannote.audio.

``diarize`` answers "who spoke when" as a flat list of turns. It does **not**
identify anyone — that is done in ``pipeline.match`` by re-embedding each cluster
and comparing to enrolled contacts.

Graceful degradation is a first-class concern: if no auth token is configured, or
the gated model cannot be loaded (access not granted / offline / download error),
``diarize`` returns ``None`` instead of raising, and the runner falls back to an
ASR-only transcript. The loaded pipeline is cached for the process lifetime.

IMPORTANT: the three HF/torch/torchaudio compat shims must be applied before any
pyannote model is constructed — we do that at import time here.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import hf_hub_compat
import pa_torchaudio_shim
import torch_load_compat

hf_hub_compat.apply_hf_hub_use_auth_token_compat()
pa_torchaudio_shim.apply_pyannote_torchaudio_shim()
torch_load_compat.apply_torch_load_compat()

from config.settings import settings
from pipeline.device import pyannote_torch_device

log = logging.getLogger(__name__)

__all__ = ["diarize", "get_diarization_pipeline"]


@lru_cache(maxsize=1)
def get_diarization_pipeline():
    """Load and cache the pyannote diarization pipeline, or return None.

    Returns None (never raises) when the token is missing or the model cannot be
    loaded, so callers can degrade to ASR-only.
    """
    if not settings.PYANNOTE_AUTH_TOKEN:
        log.warning("PYANNOTE_AUTH_TOKEN not set — diarization disabled (ASR-only).")
        return None
    try:
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(
            settings.PYANNOTE_DIARIZATION_MODEL,
            use_auth_token=settings.PYANNOTE_AUTH_TOKEN,
        )
        if pipeline is None:
            # from_pretrained returns None when the user has not accepted the
            # model's gated terms on Hugging Face.
            log.warning(
                "Diarization model %s unavailable (gated access not granted?).",
                settings.PYANNOTE_DIARIZATION_MODEL,
            )
            return None
        pipeline.to(_torch_device())
        return pipeline
    except Exception:
        log.exception("Failed to load diarization pipeline — falling back to ASR-only.")
        return None


def _torch_device():
    import torch

    return torch.device(pyannote_torch_device())


def diarize(
    audio_path: Path | str | None = None,
    num_speakers: int | None = None,
    *,
    waveform=None,
    sample_rate: int | None = None,
) -> list[dict] | None:
    """Run diarization over a recording.

    Prefers an already-decoded ``waveform`` (mono float32 ndarray + ``sample_rate``)
    so the runner decodes the audio only once; otherwise reads ``audio_path``.

    Args:
        audio_path: path to the audio file (used when no waveform is given).
        num_speakers: expected speaker count. In this closed-set app every member
            is enrolled, so the runner passes ``len(contacts)``; <= 0 means unknown.
        waveform: optional decoded mono waveform to diarize in place.
        sample_rate: sample rate of ``waveform``.

    Returns:
        A list of overlap-aware turns ``[{start, end, speaker_label}]`` ordered by
        start time, or ``None`` if diarization is unavailable (caller degrades).
    """
    pipeline = get_diarization_pipeline()
    if pipeline is None:
        return None

    try:
        kwargs: dict = {}
        if num_speakers and num_speakers > 0:
            kwargs["num_speakers"] = int(num_speakers)
        if waveform is not None and sample_rate:
            import numpy as np
            import torch

            mono = np.asarray(waveform, dtype=np.float32).reshape(-1)
            tensor = torch.from_numpy(mono).unsqueeze(0)  # shape (channel=1, time)
            annotation = pipeline({"waveform": tensor, "sample_rate": int(sample_rate)}, **kwargs)
        else:
            annotation = pipeline(str(audio_path), **kwargs)
    except Exception:
        log.exception("Diarization failed — falling back to ASR-only.")
        return None

    turns: list[dict] = []
    for segment, _track, label in annotation.itertracks(yield_label=True):
        start, end = float(segment.start), float(segment.end)
        if end <= start:
            continue
        turns.append({"start": start, "end": end, "speaker_label": str(label)})

    turns.sort(key=lambda t: (t["start"], t["end"]))
    log.info("Diarization produced %d turn(s).", len(turns))
    return turns

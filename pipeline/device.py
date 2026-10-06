"""Per-engine compute-device resolution for the single-device pipeline.

One setting (`COMPUTE_DEVICE`) picks the target, but the two ML engines have
different backends, so each needs its own resolver:

  * **pyannote** runs on PyTorch and supports ``cpu`` / ``mps`` (Apple Metal) /
    ``cuda``.
  * **faster-whisper** runs on CTranslate2, which has **no Metal backend** — it
    supports only ``cpu`` and ``cuda``. On a Mac (``mps``) the ASR therefore
    falls back to ``cpu`` / ``int8`` even though diarization/embedding use the GPU.

The decision logic is factored into small pure helpers (``_resolve_pyannote`` /
``_resolve_asr``) that take plain booleans so they can be unit-tested without a
GPU or importing torch.
"""

from __future__ import annotations

import logging
import os

from config.settings import settings

log = logging.getLogger(__name__)

__all__ = ["pyannote_torch_device", "asr_device_compute"]


def _resolve_pyannote(device: str, cuda_available: bool, mps_available: bool) -> str:
    """Pure resolver for the pyannote (PyTorch) device string.

    ``auto`` prefers cuda > mps > cpu. An explicit ``mps`` request is honoured
    only when Metal is actually available, otherwise we degrade to cpu.
    """
    device = (device or "auto").strip().lower()

    if cuda_available and device in {"auto", "cuda"}:
        return "cuda"
    if mps_available and device in {"auto", "mps"}:
        return "mps"
    return "cpu"


def _resolve_asr(device: str, cuda_available: bool, cpu_compute_type: str) -> tuple[str, str]:
    """Pure resolver for faster-whisper (CTranslate2) — never Metal.

    Returns ``("cuda", "float16")`` only when CUDA is present and requested;
    everything else (including ``mps`` on a Mac) uses ``("cpu", <cpu type>)``.
    """
    device = (device or "auto").strip().lower()

    if cuda_available and device in {"auto", "cuda"}:
        return "cuda", "float16"
    return "cpu", (cpu_compute_type or "int8")


def pyannote_torch_device() -> str:
    """Resolve the torch device string for pyannote models (cpu/mps/cuda)."""
    import torch

    cuda = bool(torch.cuda.is_available())
    mps = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())

    resolved = _resolve_pyannote(settings.COMPUTE_DEVICE, cuda, mps)
    if resolved == "mps":
        # pyannote has ops that are not yet implemented on Metal; let them fall
        # back to CPU rather than crash.
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    log.debug("pyannote device resolved to %s (cuda=%s mps=%s)", resolved, cuda, mps)
    return resolved


def asr_device_compute() -> tuple[str, str]:
    """Resolve ``(device, compute_type)`` for faster-whisper.

    On Apple Silicon this intentionally returns cpu/int8 — CTranslate2 cannot use
    Metal, so trying to run it on ``mps`` would fail.
    """
    import torch

    cuda = bool(torch.cuda.is_available())
    resolved = _resolve_asr(settings.COMPUTE_DEVICE, cuda, settings.TRANSCRIBE_COMPUTE_TYPE)
    log.debug("asr device/compute resolved to %s (cuda=%s)", resolved, cuda)
    return resolved

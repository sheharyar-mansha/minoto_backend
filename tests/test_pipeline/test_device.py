"""Pure-logic tests for the per-engine device resolvers (no torch/GPU needed)."""

from __future__ import annotations

from pipeline.device import _resolve_asr, _resolve_pyannote


# --- ASR (faster-whisper / CTranslate2 — NO Metal) --------------------------

def test_asr_uses_cpu_int8_when_no_cuda():
    assert _resolve_asr("auto", cuda_available=False, cpu_compute_type="int8") == ("cpu", "int8")


def test_asr_on_mac_mps_still_cpu():
    # mps requested but CTranslate2 can't use Metal -> cpu/int8.
    assert _resolve_asr("mps", cuda_available=False, cpu_compute_type="int8") == ("cpu", "int8")


def test_asr_uses_cuda_float16_when_available():
    assert _resolve_asr("auto", cuda_available=True, cpu_compute_type="int8") == ("cuda", "float16")
    assert _resolve_asr("cuda", cuda_available=True, cpu_compute_type="int8") == ("cuda", "float16")


def test_asr_cpu_forced_even_with_cuda():
    assert _resolve_asr("cpu", cuda_available=True, cpu_compute_type="int8") == ("cpu", "int8")


def test_asr_respects_configured_cpu_compute_type():
    assert _resolve_asr("cpu", cuda_available=False, cpu_compute_type="int8_float16") == (
        "cpu",
        "int8_float16",
    )


# --- pyannote (PyTorch — cpu/mps/cuda) --------------------------------------

def test_pyannote_auto_prefers_cuda_then_mps_then_cpu():
    assert _resolve_pyannote("auto", cuda_available=True, mps_available=True) == "cuda"
    assert _resolve_pyannote("auto", cuda_available=False, mps_available=True) == "mps"
    assert _resolve_pyannote("auto", cuda_available=False, mps_available=False) == "cpu"


def test_pyannote_explicit_mps_requires_availability():
    assert _resolve_pyannote("mps", cuda_available=False, mps_available=True) == "mps"
    assert _resolve_pyannote("mps", cuda_available=False, mps_available=False) == "cpu"


def test_pyannote_explicit_cpu():
    assert _resolve_pyannote("cpu", cuda_available=True, mps_available=True) == "cpu"


def test_pyannote_explicit_cuda_falls_back_to_cpu_without_cuda():
    assert _resolve_pyannote("cuda", cuda_available=False, mps_available=False) == "cpu"

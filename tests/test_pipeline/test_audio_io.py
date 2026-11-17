from __future__ import annotations

import numpy as np

from pipeline.audio_io import normalize_loudness, segment_rms, slice_audio

SR = 16000


def test_segment_rms_silence_is_zero():
    silence = np.zeros(SR, dtype=np.float32)
    assert segment_rms(silence, SR, 0.0, 1.0) < 1e-3


def test_segment_rms_matches_constant_amplitude():
    tone = np.full(SR, 0.5, dtype=np.float32)
    assert abs(segment_rms(tone, SR, 0.0, 1.0) - 0.5) < 1e-3


def test_segment_rms_empty_span_is_zero():
    tone = np.full(SR, 0.5, dtype=np.float32)
    assert segment_rms(tone, SR, 2.0, 3.0) == 0.0  # out of range -> no samples


def test_slice_audio_bounds():
    audio = np.arange(SR, dtype=np.float32)
    assert len(slice_audio(audio, SR, 0.0, 0.5)) == SR // 2
    assert len(slice_audio(audio, SR, 0.5, 0.0)) == 0  # end before start
    assert len(slice_audio(audio, SR, 0.9, 5.0)) == SR - int(0.9 * SR)  # clamps to end


# --- Loudness normalization -------------------------------------------------

def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x) + 1e-12))


def test_quiet_audio_is_amplified_toward_target():
    # A quiet 200 Hz tone at ~0.02 RMS should be boosted toward the target.
    t = np.arange(SR, dtype=np.float32) / SR
    quiet = (0.02 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    out, gain = normalize_loudness(quiet, target_rms=0.1, max_gain=8.0)
    assert gain > 1.0
    assert _rms(out) > _rms(quiet)


def test_never_clips():
    # Even an aggressive boost must stay within [-1, 1].
    t = np.arange(SR, dtype=np.float32) / SR
    quiet = (0.005 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    out, _ = normalize_loudness(quiet, target_rms=0.3, max_gain=50.0)
    assert float(np.max(np.abs(out))) <= 1.0


def test_already_loud_audio_is_left_alone():
    # RMS already at/above target and not hot -> no change (gain == 1).
    t = np.arange(SR, dtype=np.float32) / SR
    loud = (0.3 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    out, gain = normalize_loudness(loud, target_rms=0.1)
    assert gain == 1.0
    np.testing.assert_allclose(out, loud - np.mean(loud), atol=1e-6)


def test_hot_audio_is_tamed_under_ceiling():
    # A near-full-scale signal is pulled just under the peak ceiling.
    t = np.arange(SR, dtype=np.float32) / SR
    hot = (0.999 * np.sign(np.sin(2 * np.pi * 150 * t))).astype(np.float32)
    out, gain = normalize_loudness(hot, peak_ceiling=0.97)
    assert gain < 1.0
    assert float(np.max(np.abs(out))) <= 0.971


def test_silence_is_untouched():
    silence = np.zeros(SR, dtype=np.float32)
    out, gain = normalize_loudness(silence)
    assert gain == 1.0
    assert float(np.max(np.abs(out))) == 0.0


def test_empty_input():
    empty = np.zeros(0, dtype=np.float32)
    out, gain = normalize_loudness(empty)
    assert gain == 1.0
    assert out.size == 0


def test_dc_offset_removed():
    # A constant offset added to a tone should be centred back to ~zero mean.
    t = np.arange(SR, dtype=np.float32) / SR
    tone = (0.05 * np.sin(2 * np.pi * 200 * t) + 0.2).astype(np.float32)
    out, _ = normalize_loudness(tone)
    assert abs(float(np.mean(out))) < 1e-3


def test_length_and_dtype_preserved():
    t = np.arange(SR // 2, dtype=np.float32) / SR
    sig = (0.03 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    out, _ = normalize_loudness(sig)
    assert out.shape == sig.shape
    assert out.dtype == np.float32

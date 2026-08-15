from __future__ import annotations

import numpy as np

from pipeline.audio_io import segment_rms, slice_audio

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

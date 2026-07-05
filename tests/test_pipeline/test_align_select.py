from __future__ import annotations

import numpy as np

from pipeline.align.gcc_phat import gcc_phat_offset_sec
from pipeline.select.channel_selection import select_best_channels
from pipeline.types import SpeechRegion
from pipeline.vad.energy_vad import energy_vad_regions


def test_gcc_phat_finds_known_offset():
    sr = 16000
    t = np.linspace(0, 2, sr * 2, endpoint=False)
    ref = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    delay_samples = 800
    sig = np.zeros_like(ref)
    sig[delay_samples:] = ref[:-delay_samples]
    off = gcc_phat_offset_sec(ref, sig, sr, max_lag_sec=0.2)
    expected = delay_samples / sr
    assert abs(off - expected) < 0.16


def test_channel_selection_picks_louder_near_field():
    regions = [
        SpeechRegion("a", "user-a", 0.0, 1.0, energy=0.1),
        SpeechRegion("b", "user-b", 0.0, 1.0, energy=0.9),
    ]
    picked = select_best_channels(regions)
    assert picked
    assert picked[0].channel_id == "b"

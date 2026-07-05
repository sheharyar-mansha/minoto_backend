from __future__ import annotations

import numpy as np

from pipeline.types import SpeechRegion


def energy_vad_regions(
    audio: np.ndarray,
    sr: int,
    channel_id: str,
    uploader_user_id: str,
    frame_ms: int = 30,
    hop_ms: int = 15,
    threshold_ratio: float = 0.15,
    min_region_sec: float = 0.35,
) -> list[SpeechRegion]:
    if len(audio) == 0:
        return []
    frame = int(sr * frame_ms / 1000)
    hop = int(sr * hop_ms / 1000)
    if frame <= 0 or hop <= 0:
        return []
    energies: list[tuple[float, float]] = []
    for start in range(0, len(audio) - frame + 1, hop):
        chunk = audio[start : start + frame]
        e = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
        t0 = start / sr
        t1 = (start + frame) / sr
        energies.append((t0, e))
    if not energies:
        return []
    peak = max(e for _, e in energies)
    thr = peak * threshold_ratio
    regions: list[SpeechRegion] = []
    active_start: float | None = None
    for (t0, e), (t0_next, _) in zip(energies, energies[1:] + [(energies[-1][0] + frame / sr, 0.0)]):
        if e >= thr and active_start is None:
            active_start = t0
        elif e < thr and active_start is not None:
            end = t0_next
            if end - active_start >= min_region_sec:
                regions.append(
                    SpeechRegion(
                        channel_id=channel_id,
                        uploader_user_id=uploader_user_id,
                        start_sec=active_start,
                        end_sec=end,
                        energy=peak,
                    )
                )
            active_start = None
    return regions

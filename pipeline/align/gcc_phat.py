from __future__ import annotations

import numpy as np
from scipy.signal import correlate, correlation_lags


def gcc_phat_offset_sec(
    ref: np.ndarray,
    sig: np.ndarray,
    sr: int,
    max_lag_sec: float = 5.0,
) -> float:
    """Estimate time offset (seconds) to add to sig so it aligns with ref."""
    if len(ref) < sr or len(sig) < sr:
        return 0.0
    n = min(len(ref), len(sig), sr * 30)
    a = ref[:n].astype(np.float64)
    b = sig[:n].astype(np.float64)
    a -= a.mean()
    b -= b.mean()
    if np.allclose(a, 0) or np.allclose(b, 0):
        return 0.0
    fa = np.fft.rfft(a)
    fb = np.fft.rfft(b)
    cross = fa * np.conj(fb)
    cross /= np.maximum(np.abs(cross), 1e-8)
    cc = np.fft.irfft(cross)
    cc = np.concatenate((cc[len(cc) // 2 :], cc[: len(cc) // 2]))
    max_lag = int(max_lag_sec * sr)
    center = len(cc) // 2
    lo = max(0, center - max_lag)
    hi = min(len(cc), center + max_lag + 1)
    window = cc[lo:hi]
    lag_idx = np.argmax(window) + lo - center
    return lag_idx / float(sr)


def align_channels(
    channels: dict[str, tuple[np.ndarray, int]],
    reference_id: str,
) -> dict[str, float]:
    """Return per-channel offset seconds relative to reference channel."""
    if reference_id not in channels:
        reference_id = next(iter(channels))
    ref_audio, sr = channels[reference_id]
    offsets: dict[str, float] = {reference_id: 0.0}
    for cid, (audio, _sr) in channels.items():
        if cid == reference_id:
            continue
        offsets[cid] = gcc_phat_offset_sec(ref_audio, audio, sr)
    return offsets

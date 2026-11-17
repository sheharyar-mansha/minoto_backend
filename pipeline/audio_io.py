from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from utils.ffmpeg_bin import ffmpeg_executable, probe_duration_sec

__all__ = [
    "load_mono_wav",
    "normalize_loudness",
    "probe_duration_sec",
    "slice_audio",
    "segment_rms",
]


def load_mono_wav(path: Path, target_sr: int = 16000) -> tuple[np.ndarray, int]:
    """Decode any supported audio to mono float32 via ffmpeg."""
    cmd = [
        ffmpeg_executable(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(target_sr),
        "-f",
        "f32le",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace") or "ffmpeg failed")
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    return audio, target_sr


def normalize_loudness(
    audio: np.ndarray,
    target_rms: float = 0.1,
    peak_ceiling: float = 0.97,
    max_gain: float = 8.0,
    noise_floor_rms: float = 1e-4,
) -> tuple[np.ndarray, float]:
    """Bring a mono float32 waveform to a consistent loudness without clipping.

    This is deliberately gentle — it is NOT a raw "turn the volume up", which would
    clip loud recordings into distortion and *hurt* transcription. Instead it:

    1. Removes any DC offset (centres the waveform on zero).
    2. Computes the gain needed to reach ``target_rms``, but caps it by the gain
       that just touches ``peak_ceiling`` (so a loud transient can never force
       clipping) and by ``max_gain`` (so near-silence/noise isn't blown up).
    3. Only ever *amplifies* quiet audio (gain >= 1). An already-loud recording is
       left untouched; a hot/near-clipping one is gently pulled back under the
       ceiling.

    Near-silent audio (below ``noise_floor_rms``) is returned unchanged, since
    amplifying it would only raise the noise floor.

    Returns the processed waveform and the gain that was applied (1.0 == no change).
    """
    if audio.size == 0:
        return audio, 1.0
    x = audio.astype(np.float32, copy=True)
    x -= np.float32(np.mean(x))  # DC offset removal

    rms = float(np.sqrt(np.mean(x * x) + 1e-12))
    peak = float(np.max(np.abs(x)) + 1e-12)

    if rms < noise_floor_rms:
        return x, 1.0  # essentially silence — leave it alone

    if peak > peak_ceiling:
        gain = peak_ceiling / peak  # tame a hot/near-clipping recording
    else:
        gain = min(target_rms / rms, peak_ceiling / peak, max_gain)
        gain = max(gain, 1.0)  # only amplify quiet audio; never attenuate good audio

    if gain == 1.0:
        return x, 1.0

    y = x * np.float32(gain)
    np.clip(y, -1.0, 1.0, out=y)  # belt-and-braces; the peak guard already prevents clipping
    return y.astype(np.float32, copy=False), float(gain)


def slice_audio(audio: np.ndarray, sr: int, start_sec: float, end_sec: float) -> np.ndarray:
    s = max(0, int(start_sec * sr))
    e = min(len(audio), int(end_sec * sr))
    if e <= s:
        return np.zeros(0, dtype=np.float32)
    return audio[s:e]


def segment_rms(audio: np.ndarray, sr: int, start_sec: float, end_sec: float) -> float:
    """RMS loudness of one time span."""
    seg = slice_audio(audio, sr, start_sec, end_sec)
    if seg.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(seg * seg) + 1e-12))

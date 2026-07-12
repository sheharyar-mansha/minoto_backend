from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from utils.ffmpeg_bin import ffmpeg_executable, probe_duration_sec

__all__ = ["load_mono_wav", "probe_duration_sec", "slice_audio", "segment_rms"]


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


def slice_audio(audio: np.ndarray, sr: int, start_sec: float, end_sec: float) -> np.ndarray:
    s = max(0, int(start_sec * sr))
    e = min(len(audio), int(end_sec * sr))
    if e <= s:
        return np.zeros(0, dtype=np.float32)
    return audio[s:e]


def segment_rms(audio: np.ndarray, sr: int, start_sec: float, end_sec: float) -> float:
    """RMS loudness of one time span — a cheap proximity proxy for cross-device dedup."""
    seg = slice_audio(audio, sr, start_sec, end_sec)
    if seg.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(seg * seg) + 1e-12))

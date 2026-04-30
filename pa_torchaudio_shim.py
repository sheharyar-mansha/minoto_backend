"""
Pyannote 3.1 expects torchaudio.AudioMetaData, torchaudio.info, and
torchaudio.list_audio_backends. TorchAudio 2.9+ (TorchCodec backend) removed
these from the top-level module. Patch them in-place before importing pyannote.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Any, BinaryIO, Union

_applied = False


def apply_pyannote_torchaudio_shim() -> None:
    global _applied
    if _applied:
        return

    import torchaudio

    if (
        hasattr(torchaudio, "AudioMetaData")
        and hasattr(torchaudio, "info")
        and hasattr(torchaudio, "list_audio_backends")
    ):
        _applied = True
        return

    from dataclasses import dataclass

    @dataclass
    class AudioMetaData:
        sample_rate: int
        num_frames: int
        num_channels: int
        bits_per_sample: int = 16
        encoding: str = "PCM_S"

    torchaudio.AudioMetaData = AudioMetaData  # type: ignore[attr-defined]

    if not hasattr(torchaudio, "list_audio_backends"):

        def list_audio_backends() -> list[str]:
            return ["soundfile", "ffmpeg"]

        torchaudio.list_audio_backends = list_audio_backends  # type: ignore[attr-defined]

    if not hasattr(torchaudio, "info"):

        def info(
            path: Union[str, Path, BinaryIO],
            backend: str | None = None,
        ) -> Any:
            del backend  # pyannote passes it; TorchCodec path ignores it
            if hasattr(path, "read"):
                raise TypeError("torchaudio.info shim only supports file paths")
            p = Path(path)
            if not p.is_file():
                raise FileNotFoundError(str(p))
            if p.suffix.lower() == ".wav":
                with wave.open(str(p), "rb") as w:
                    ch = w.getnchannels()
                    sw = w.getsampwidth()
                    sr = w.getframerate()
                    nf = w.getnframes()
                return AudioMetaData(
                    sample_rate=sr,
                    num_frames=nf,
                    num_channels=ch,
                    bits_per_sample=sw * 8,
                )
            try:
                import soundfile as sf  # type: ignore[import-untyped]

                inf = sf.info(str(p))
                return AudioMetaData(
                    sample_rate=int(inf.samplerate),
                    num_frames=int(inf.frames),
                    num_channels=int(inf.channels),
                    bits_per_sample=16,
                )
            except ImportError as e:
                raise RuntimeError(
                    "Install soundfile for torchaudio.info shim on non-WAV files: pip install soundfile"
                ) from e

        torchaudio.info = info  # type: ignore[attr-defined]

    _applied = True

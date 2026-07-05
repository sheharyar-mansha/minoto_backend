from __future__ import annotations

import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from functools import lru_cache

from config.settings import settings
from pipeline.types import TranscriptSegmentDraft, WordToken
from utils.ffmpeg_bin import ffmpeg_executable


class AsrBackend(ABC):
    @abstractmethod
    def transcribe_slice(
        self,
        audio_path: Path,
        start_sec: float,
        end_sec: float,
        recording_id: str,
        uploader_user_id: str,
    ) -> TranscriptSegmentDraft | None:
        raise NotImplementedError


class FasterWhisperBackend(AsrBackend):
    def __init__(self) -> None:
        self._model = None

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                settings.TRANSCRIBE_MODEL_SIZE,
                device=settings.TRANSCRIBE_DEVICE,
                compute_type=settings.TRANSCRIBE_COMPUTE_TYPE,
            )
        return self._model

    def transcribe_slice(
        self,
        audio_path: Path,
        start_sec: float,
        end_sec: float,
        recording_id: str,
        uploader_user_id: str,
    ) -> TranscriptSegmentDraft | None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            out = Path(tmp.name)
        try:
            dur = max(0.1, end_sec - start_sec)
            cmd = [
                ffmpeg_executable(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(start_sec),
                "-t",
                str(dur),
                "-i",
                str(audio_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-y",
                str(out),
            ]
            proc = subprocess.run(cmd, capture_output=True, check=False)
            if proc.returncode != 0:
                return None
            model = self._get_model()
            segments, _info = model.transcribe(str(out), vad_filter=True)
            parts: list[str] = []
            words: list[WordToken] = []
            confidences: list[float] = []
            for seg in segments:
                parts.append(seg.text.strip())
                confidences.append(getattr(seg, "avg_logprob", 0.0) or 0.0)
                if seg.words:
                    for w in seg.words:
                        words.append(
                            WordToken(
                                word=w.word.strip(),
                                start=start_sec + float(w.start or 0),
                                end=start_sec + float(w.end or 0),
                            )
                        )
            text = " ".join(p for p in parts if p).strip()
            if not text:
                return None
            avg_conf = float(sum(confidences) / len(confidences)) if confidences else None
            return TranscriptSegmentDraft(
                start_sec=start_sec,
                end_sec=end_sec,
                text=text,
                speaker_user_id=uploader_user_id,
                source_recording_id=recording_id,
                source_uploader_user_id=uploader_user_id,
                confidence=avg_conf,
                match_status="matched",
                words=words,
            )
        finally:
            out.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def get_asr_backend() -> AsrBackend:
    backend = (settings.ASR_BACKEND or "faster_whisper").strip().lower()
    if backend != "faster_whisper":
        raise ValueError(
            f"Unsupported ASR_BACKEND={backend!r}. Only faster_whisper is implemented."
        )
    return FasterWhisperBackend()

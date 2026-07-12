from __future__ import annotations

import math
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from functools import lru_cache

import numpy as np

from config.settings import settings
from pipeline.types import TranscriptSegmentDraft, WordToken
from utils.ffmpeg_bin import ffmpeg_executable


def _is_degenerate(text: str) -> bool:
    """True for Whisper's runaway loops (e.g. "you you you you") — never real speech."""
    toks = text.split()
    if len(toks) >= 4 and len(set(t.lower() for t in toks)) == 1:
        return True
    return False


class AsrBackend(ABC):
    @abstractmethod
    def transcribe_file(
        self,
        audio: np.ndarray,
        sr: int,
        recording_id: str,
        uploader_user_id: str,
        initial_prompt: str | None = None,
    ) -> list[TranscriptSegmentDraft]:
        """Transcribe one device's whole recording (local time), context-aware."""
        raise NotImplementedError

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

    def transcribe_file(
        self,
        audio: np.ndarray,
        sr: int,
        recording_id: str,
        uploader_user_id: str,
        initial_prompt: str | None = None,
    ) -> list[TranscriptSegmentDraft]:
        if audio is None or getattr(audio, "size", 0) == 0:
            return []
        # faster-whisper wants mono float32 @ 16 kHz; upstream (load_mono_wav) already gives us that.
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)

        language = (settings.TRANSCRIBE_LANGUAGE or "").strip().lower()
        model = self._get_model()
        segments, _info = model.transcribe(
            samples,
            language=language or None,
            task="transcribe",
            beam_size=max(1, settings.TRANSCRIBE_BEAM_SIZE),
            # One VAD pass over the WHOLE file (not per fragment) keeps Whisper's context intact.
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200},
            # Feed each 30s window the previous text so wording/punctuation stay coherent.
            condition_on_previous_text=True,
            word_timestamps=True,
            initial_prompt=initial_prompt,
            # Anti-hallucination: escalate temperature only on failure, and drop
            # empty/gibberish/silent windows instead of inventing "Thank you." etc.
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
        )

        drafts: list[TranscriptSegmentDraft] = []
        for seg in segments:
            text = (seg.text or "").strip()
            if not text or _is_degenerate(text):
                continue
            avg_lp = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
            no_speech = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
            if no_speech > 0.9:  # belt-and-suspenders over Whisper's own gate
                continue
            words: list[WordToken] = []
            for w in (seg.words or []):
                token = (w.word or "").strip()
                if not token:
                    continue
                words.append(
                    WordToken(
                        word=token,
                        start=float(w.start if w.start is not None else seg.start),
                        end=float(w.end if w.end is not None else seg.end),
                    )
                )
            drafts.append(
                TranscriptSegmentDraft(
                    start_sec=float(seg.start),
                    end_sec=float(seg.end),
                    text=text,
                    speaker_user_id=uploader_user_id,
                    source_recording_id=recording_id,
                    source_uploader_user_id=uploader_user_id,
                    # avg_logprob is a log-prob; expose it as a 0..1 confidence.
                    confidence=float(math.exp(avg_lp)) if avg_lp else None,
                    no_speech_prob=no_speech,
                    match_status="matched",
                    words=words,
                )
            )
        return drafts

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

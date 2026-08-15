from __future__ import annotations

from functools import lru_cache

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import hf_hub_compat
import numpy as np
import pa_torchaudio_shim
import torch_load_compat

hf_hub_compat.apply_hf_hub_use_auth_token_compat()
pa_torchaudio_shim.apply_pyannote_torchaudio_shim()
torch_load_compat.apply_torch_load_compat()

from config.settings import settings
from pipeline.audio_io import load_mono_wav, slice_audio

log = logging.getLogger(__name__)

EMBEDDING_DIM = 512


def embedding_to_vector(emb: object, dim: int = EMBEDDING_DIM) -> np.ndarray | None:
    """Collapse pyannote outputs (SlidingWindowFeature, tensors, etc.) to one vector."""
    try:
        from pyannote.core import SlidingWindowFeature

        if isinstance(emb, SlidingWindowFeature):
            data = np.asarray(emb.data, dtype=np.float32)
            if data.size == 0:
                return None
            if data.ndim == 1:
                return normalize_embedding_vector(data, dim)
            return normalize_embedding_vector(data.mean(axis=0), dim)
    except ImportError:
        pass

    if hasattr(emb, "detach"):
        arr = emb.detach().cpu().numpy()
    else:
        arr = np.asarray(emb, dtype=np.float32)
    return normalize_embedding_vector(arr, dim)


def normalize_embedding_vector(vec: np.ndarray | None, dim: int = EMBEDDING_DIM) -> np.ndarray | None:
    if vec is None:
        return None
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    if len(v) == 0:
        return None
    if len(v) == dim:
        return v
    if len(v) > dim and len(v) % dim == 0:
        return v.reshape(-1, dim).mean(axis=0)
    return v


class EmbeddingBackend(ABC):
    @abstractmethod
    def embed_span(self, audio: np.ndarray, sr: int, start_sec: float, end_sec: float) -> np.ndarray | None:
        """Embed a time span of an already-decoded waveform (no file re-read)."""
        raise NotImplementedError

    @abstractmethod
    def embed_slice(self, path: Path, start_sec: float, end_sec: float) -> np.ndarray | None:
        raise NotImplementedError

    @abstractmethod
    def embed_enrollment(self, path: Path) -> np.ndarray | None:
        raise NotImplementedError


class PyannoteEmbeddingBackend(EmbeddingBackend):
    def __init__(self) -> None:
        self._model = None

    def _get_model(self):
        if self._model is None:
            if not settings.PYANNOTE_AUTH_TOKEN:
                raise RuntimeError("PYANNOTE_AUTH_TOKEN is required for speaker matching.")
            from pyannote.audio import Inference

            self._model = Inference(
                settings.PYANNOTE_EMBEDDING_MODEL,
                use_auth_token=settings.PYANNOTE_AUTH_TOKEN,
                window="whole",
            )
        return self._model

    def embed_span(self, audio: np.ndarray, sr: int, start_sec: float, end_sec: float) -> np.ndarray | None:
        if end_sec - start_sec < settings.SPEAKER_MATCH_MIN_SEGMENT_SEC:
            return None
        chunk = slice_audio(audio, sr, start_sec, end_sec)
        if len(chunk) < int(sr * 0.3):
            return None
        return self._embed_waveform(chunk, sr)

    def embed_slice(self, path: Path, start_sec: float, end_sec: float) -> np.ndarray | None:
        audio, sr = load_mono_wav(path)
        return self.embed_span(audio, sr, start_sec, end_sec)

    def embed_enrollment(self, path: Path) -> np.ndarray | None:
        audio, sr = load_mono_wav(path)
        if len(audio) < int(sr * 0.5):
            return None
        return self._embed_waveform(audio, sr)

    def _embed_waveform(self, waveform: np.ndarray, sr: int) -> np.ndarray | None:
        import torch

        model = self._get_model()
        mono = np.asarray(waveform, dtype=np.float32).reshape(-1).copy()
        if len(mono) == 0:
            return None
        # pyannote Inference expects waveform shape (channel, time), not batched.
        tensor = torch.from_numpy(mono).unsqueeze(0)
        if tensor.dim() != 2 or tensor.shape[0] > tensor.shape[1]:
            return None
        with torch.no_grad():
            emb = model({"waveform": tensor, "sample_rate": int(sr)})
        return embedding_to_vector(emb)


@lru_cache(maxsize=1)
def get_embedding_backend() -> EmbeddingBackend:
    backend = (settings.EMBEDDING_BACKEND or "pyannote").strip().lower()
    if backend != "pyannote":
        raise ValueError(
            f"Unsupported EMBEDDING_BACKEND={backend!r}. Only pyannote is implemented."
        )
    return PyannoteEmbeddingBackend()


def serialize_embedding(vec: np.ndarray) -> str:
    return json.dumps(vec.astype(float).tolist())


def deserialize_embedding(raw: str | None) -> np.ndarray | None:
    if not raw:
        return None
    try:
        return normalize_embedding_vector(np.asarray(json.loads(raw), dtype=np.float32))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

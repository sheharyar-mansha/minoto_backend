from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Minoto API"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    DATABASE_URL: str = "sqlite:///./minoto.db"  # dev default; prod uses PostgreSQL in .env

    SECRET_KEY: str = "minoto-localhost-dev-jwt-secret-do-not-use-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    UPLOAD_ROOT: str = "uploads"
    MAX_VOICE_UPLOAD_MB: int = 25

    # --- Pipeline (single-device) ---
    PIPELINE_VERSION: str = "v3.0.0"

    # Compute target. One knob picks the device for every model; the per-engine
    # resolver (pipeline/device.py) adapts it because the engines differ:
    #   - faster-whisper (CTranslate2) supports only cpu/cuda (NO Metal) -> on a
    #     Mac, ASR runs on cpu/int8 even when COMPUTE_DEVICE=mps.
    #   - pyannote (PyTorch) supports cpu/mps/cuda.
    # "auto" => cuda if available, else mps if available, else cpu.
    COMPUTE_DEVICE: str = "auto"  # auto | cpu | mps | cuda
    TRANSCRIBE_MODEL_SIZE: str = "small"  # small (Mac dev) | medium | large-v3 | distil-large-v3 (GPU)
    TRANSCRIBE_COMPUTE_TYPE: str = "int8"  # CPU int8; CUDA float16 (resolved in device.py)
    TRANSCRIBE_LANGUAGE: str = "en"  # "" / "auto" to auto-detect
    TRANSCRIBE_BEAM_SIZE: int = 5

    # Speaker identification (match diarized clusters to enrolled contacts).
    PYANNOTE_DIARIZATION_MODEL: str = "pyannote/speaker-diarization-3.1"
    PYANNOTE_EMBEDDING_MODEL: str = "pyannote/embedding"  # 512-dim, used for BOTH enrollment and match
    PYANNOTE_AUTH_TOKEN: str | None = None  # needs the gated diarization models accepted on HF
    SPEAKER_MATCH_MIN_SCORE: float = 0.35  # min cosine to accept a cluster->contact match
    SPEAKER_MATCH_MIN_MARGIN: float = 0.05  # best match must beat 2nd-best by this much
    SPEAKER_MATCH_MIN_SEGMENT_SEC: float = 0.8  # ignore sub-second snippets when embedding

    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"


settings = Settings()

UPLOAD_DIR = Path(__file__).resolve().parent.parent / settings.UPLOAD_ROOT

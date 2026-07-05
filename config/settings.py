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

    DATABASE_URL: str = "sqlite:///./minoto.db"

    SECRET_KEY: str = "minoto-localhost-dev-jwt-secret-do-not-use-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    UPLOAD_ROOT: str = "uploads"
    MAX_VOICE_UPLOAD_MB: int = 25

    # Pipeline v2
    PIPELINE_VERSION: str = "v2.0.0"
    ASR_BACKEND: str = "faster_whisper"
    EMBEDDING_BACKEND: str = "pyannote"
    TRANSCRIBE_MODEL_SIZE: str = "small"
    TRANSCRIBE_DEVICE: str = "cpu"
    TRANSCRIBE_COMPUTE_TYPE: str = "int8"
    ENABLE_SPEAKER_MATCHING: bool = True
    SPEAKER_MATCH_MIN_SCORE: float = 0.32
    SPEAKER_MATCH_UPLOADER_MIN_SCORE: float = 0.18
    SPEAKER_DEVICE_PRIOR_BONUS: float = 0.06
    SPEAKER_MATCH_MIN_SEGMENT_SEC: float = 0.8
    PYANNOTE_EMBEDDING_MODEL: str = "pyannote/embedding"
    PYANNOTE_AUTH_TOKEN: str | None = None

    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"


settings = Settings()

UPLOAD_DIR = Path(__file__).resolve().parent.parent / settings.UPLOAD_ROOT

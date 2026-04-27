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

    # Default: SQLite in backend folder for zero-config local dev. Override with Postgres in prod.
    DATABASE_URL: str = "sqlite:///./minoto.db"

    # Dev default for localhost JWT signing (no .env entry needed). Override via env when you deploy.
    SECRET_KEY: str = "minoto-localhost-dev-jwt-secret-do-not-use-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Voice uploads stored under this directory (created at startup).
    UPLOAD_ROOT: str = "uploads"
    MAX_VOICE_UPLOAD_MB: int = 25
    TRANSCRIBE_MODEL_SIZE: str = "base"
    TRANSCRIBE_DEVICE: str = "cpu"
    TRANSCRIBE_COMPUTE_TYPE: str = "int8"
    ENABLE_SPEAKER_MATCHING: bool = True
    SPEAKER_MATCH_MIN_SCORE: float = 0.58
    SPEAKER_MATCH_MARGIN: float = 0.06
    SPEAKER_MATCH_MAX_GAP_SEC: float = 1.25
    SPEAKER_MATCH_TEXT_SIMILARITY: float = 0.86
    PYANNOTE_EMBEDDING_MODEL: str = "pyannote/embedding"
    PYANNOTE_AUTH_TOKEN: str | None = None


settings = Settings()

# Resolved absolute path for file storage
UPLOAD_DIR = Path(__file__).resolve().parent.parent / settings.UPLOAD_ROOT

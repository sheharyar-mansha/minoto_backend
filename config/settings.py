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
    # Decode quality. Language "en" stops Whisper re-detecting (and flipping) per chunk;
    # set "" / "auto" to auto-detect. Beam search > greedy for accuracy.
    TRANSCRIBE_LANGUAGE: str = "en"
    TRANSCRIBE_BEAM_SIZE: int = 5
    # Cross-device time alignment: independent phones share no clock, and waveform
    # correlation fails for near-field mics, so we align on the WORDS the phones both
    # captured (see pipeline/align/text_align.py).
    ALIGN_MIN_ANCHOR_SIM: float = 0.60    # word-overlap for a phrase to count as a shared anchor
    ALIGN_MIN_ANCHOR_WORDS: int = 3       # ignore tiny phrases ("hi", "okay") as anchors
    ALIGN_MIN_ANCHORS: int = 2            # need this many phrase matches before trusting the offset
    ALIGN_INLIER_BAND_SEC: float = 1.0    # keep anchor deltas within this band of the median (reject outliers)
    # Cross-device de-duplication: the same words are captured by every phone in the
    # room. We keep the nearest/clearest mic and drop the echoes from the others.
    DEDUP_TIME_SLACK_SEC: float = 0.75    # treat segments within this gap as overlapping (absorbs residual drift)
    DEDUP_HIGH_TIME_IOU: float = 0.60     # near-identical timing -> echo even if the far mic garbled the words
    DEDUP_MIN_TEXT_SIM: float = 0.50      # word-overlap ratio that marks two lines as the same utterance
    DEDUP_LOW_TEXT_SIM: float = 0.18      # below this the texts are different speech -> keep both (crosstalk)
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

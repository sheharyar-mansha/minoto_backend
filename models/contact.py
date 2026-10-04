from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Contact(Base):
    """A person who can attend meetings — a reusable, non-login contact.

    The voice intro is recorded once and reused across every meeting. It serves
    two purposes:
      1. `voice_embedding_json` — a 512-dim pyannote/embedding vector used to
         IDENTIFY this person in a meeting recording.
      2. `spoken_name` — the name the person actually says in the guided intro
         ("Hi, my name is ___"), used to label them in the transcript. If we
         could not extract it, the transcript falls back to `name` (shown red).
    """

    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))  # roster name; may repeat
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Voice enrollment (the guided intro sample).
    has_voice_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    voice_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voice_embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_recorded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Name extracted from the intro audio (not the roster name above).
    spoken_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # How spoken_name was derived: 'intro_regex' | 'intro_gemini' | None (failed).
    spoken_name_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    meetings = relationship(
        "Meeting", secondary="meeting_contacts", back_populates="contacts"
    )

    @property
    def voice_sample_url(self) -> str | None:
        if not self.has_voice_sample or not self.voice_file_path:
            return None
        return self.voice_file_path

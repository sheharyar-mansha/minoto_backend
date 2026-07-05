from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="participant", index=True)
    default_export_format: Mapped[str] = mapped_column(String(32), default="pdf")
    include_timestamps_default: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    has_voice_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    voice_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voice_embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    meetings = relationship("Meeting", back_populates="owner", cascade="all, delete-orphan")
    meeting_participations = relationship(
        "MeetingParticipant",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    live_session = relationship(
        "MeetingLiveSession",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def voice_sample_url(self) -> str | None:
        if not self.has_voice_sample or not self.voice_file_path:
            return None
        return self.voice_file_path

    def is_admin(self) -> bool:
        return (self.role or "").strip().lower() == "admin"

    def is_participant(self) -> bool:
        role = (self.role or "").strip().lower()
        return role in ("participant", "member", "host")

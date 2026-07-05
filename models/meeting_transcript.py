from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class MeetingTranscript(Base):
    """Final merged transcript generation state for one meeting."""

    __tablename__ = "meeting_transcripts"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    pipeline_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pipeline_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    merged_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    minutes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    meeting = relationship("Meeting", back_populates="transcript")

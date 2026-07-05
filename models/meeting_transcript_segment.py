from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class MeetingTranscriptSegment(Base):
    """One transcript segment aligned to meeting timeline and speaker identity."""

    __tablename__ = "meeting_transcript_segments"
    __table_args__ = (
        Index("ix_meeting_transcript_segments_meeting_start", "meeting_id", "start_sec"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    uploader_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_uploader_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_recording_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    matched_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_status: Mapped[str] = mapped_column(String(32), default="matched")
    start_sec: Mapped[float] = mapped_column(Float, default=0)
    end_sec: Mapped[float] = mapped_column(Float, default=0)
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_timestamps_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    meeting = relationship("Meeting")
    uploader = relationship("User", foreign_keys=[uploader_user_id])
    source_uploader = relationship("User", foreign_keys=[source_uploader_user_id])
    matched_user = relationship("User", foreign_keys=[matched_user_id])

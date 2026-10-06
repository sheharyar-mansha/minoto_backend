from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class MeetingTranscriptSegment(Base):
    """One attributed line of the transcript.

    Each segment is matched (by voice) to an enrolled `Contact`. The label shown
    in the app is in `label_name`; the mobile app renders it RED when the name is
    a roster fallback (`name_source == 'fallback'`) or the speaker could not be
    confidently identified (`match_status == 'unknown'`).
    """

    __tablename__ = "meeting_transcript_segments"
    __table_args__ = (
        Index("ix_meeting_transcript_segments_meeting_start", "meeting_id", "start_sec"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    matched_contact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    label_name: Mapped[str] = mapped_column(String(255))  # rendered speaker name
    name_source: Mapped[str] = mapped_column(String(16), default="spoken")  # 'spoken' | 'fallback'
    match_status: Mapped[str] = mapped_column(String(16), default="matched")  # 'matched' | 'unknown'
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_contact_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON top-2
    is_overlap: Mapped[bool] = mapped_column(Boolean, default=False)

    # Spoken "expunge" commands (see pipeline.expunge):
    #   is_command  — this utterance IS the command (e.g. "expunge my last
    #                 statement"); hidden from the transcript and the minutes.
    #   is_expunged — a statement a command redacted; kept and shown (blue) but
    #                 excluded from the AI minutes.
    is_command: Mapped[bool] = mapped_column(Boolean, default=False)
    is_expunged: Mapped[bool] = mapped_column(Boolean, default=False)

    start_sec: Mapped[float] = mapped_column(Float, default=0)
    end_sec: Mapped[float] = mapped_column(Float, default=0)
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_timestamps_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    meeting = relationship("Meeting", back_populates="segments")
    matched_contact = relationship("Contact")

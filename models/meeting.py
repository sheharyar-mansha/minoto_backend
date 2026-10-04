from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Meeting(Base):
    """A scheduled or completed meeting.

    Single-owner app, so there is no per-user ownership. `scheduled_at` is the
    combined date+time instant — used to reject scheduling in the past and to
    order the Meetings/Archive lists.
    """

    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    meeting_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[str] = mapped_column(String(8))  # "HH:MM:SS"
    duration_minutes: Mapped[int] = mapped_column(Integer)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)
    conducted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    final_elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    contacts = relationship(
        "Contact", secondary="meeting_contacts", back_populates="meetings"
    )
    recording = relationship(
        "MeetingRecording",
        back_populates="meeting",
        uselist=False,
        cascade="all, delete-orphan",
    )
    transcript = relationship(
        "MeetingTranscript",
        back_populates="meeting",
        uselist=False,
        cascade="all, delete-orphan",
    )
    segments = relationship(
        "MeetingTranscriptSegment",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )

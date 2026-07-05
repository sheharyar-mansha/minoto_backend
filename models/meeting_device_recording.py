from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class MeetingDeviceRecording(Base):
    """One uploaded audio file from one device/user for a meeting."""

    __tablename__ = "meeting_device_recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    uploader_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    device_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    recording_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recording_ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    device_meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    meeting = relationship("Meeting", back_populates="device_recordings")
    uploader = relationship("User")

    @property
    def media_path(self) -> str:
        return self.file_path

    @property
    def participant_member_id(self) -> None:
        """Legacy mobile field — participants are users now."""
        return None

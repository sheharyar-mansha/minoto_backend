from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    member_since: Mapped[date | None] = mapped_column(Date, nullable=True)
    saved_to_directory: Mapped[bool] = mapped_column(Boolean, default=True)

    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    has_voice_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    voice_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", back_populates="members")
    meeting_links = relationship(
        "MeetingMemberLink", back_populates="member", cascade="all, delete-orphan"
    )

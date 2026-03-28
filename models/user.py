from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    default_export_format: Mapped[str] = mapped_column(String(32), default="pdf")
    include_timestamps_default: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    members = relationship("Member", back_populates="owner", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="owner", cascade="all, delete-orphan")
    live_session = relationship(
        "MeetingLiveSession",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

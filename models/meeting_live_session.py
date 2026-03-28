from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class MeetingLiveSession(Base):
    """
    At most one row per user: persisted in-app recording timer (mobile syncs here later).
    """

    __tablename__ = "meeting_live_sessions"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    running_since_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_target_seconds: Mapped[int] = mapped_column(Integer, default=0)

    user = relationship("User", back_populates="live_session")
    meeting = relationship("Meeting")

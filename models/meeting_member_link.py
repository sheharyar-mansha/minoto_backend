from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class MeetingMemberLink(Base):
    """Association: which members are on a meeting, and if they are new (not in directory)."""

    __tablename__ = "meeting_members"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    )
    is_new_for_meeting: Mapped[bool] = mapped_column(Boolean, default=False)

    meeting = relationship("Meeting", back_populates="member_links")
    member = relationship("Member", back_populates="meeting_links")

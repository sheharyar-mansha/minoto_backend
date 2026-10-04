from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class User(Base):
    """The single app owner — the only login account.

    There are no roles and no participant users anymore. Meeting attendees are
    non-login `Contact` rows. Exactly one User exists, seeded by the initial
    migration (owner@minoto.com).
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))

    # Preferences (surfaced on the Info tab).
    default_export_format: Mapped[str] = mapped_column(String(32), default="pdf")
    include_timestamps_default: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

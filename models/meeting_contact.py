"""Join table linking meetings to their attending contacts (many-to-many)."""

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, func

from db.base import Base

meeting_contacts = Table(
    "meeting_contacts",
    Base.metadata,
    Column("meeting_id", String(36), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True),
    Column("contact_id", String(36), ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime, server_default=func.now(), nullable=False),
)

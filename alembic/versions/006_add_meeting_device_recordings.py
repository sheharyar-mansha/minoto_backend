"""add meeting device recordings table

Revision ID: 006
Revises: 005
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meeting_device_recordings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("uploader_user_id", sa.String(length=36), nullable=False),
        sa.Column("participant_member_id", sa.String(length=36), nullable=True),
        sa.Column("device_label", sa.String(length=128), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploader_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_member_id"], ["members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_meeting_device_recordings_meeting_id",
        "meeting_device_recordings",
        ["meeting_id"],
    )
    op.create_index(
        "ix_meeting_device_recordings_uploader_user_id",
        "meeting_device_recordings",
        ["uploader_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_meeting_device_recordings_uploader_user_id", table_name="meeting_device_recordings")
    op.drop_index("ix_meeting_device_recordings_meeting_id", table_name="meeting_device_recordings")
    op.drop_table("meeting_device_recordings")

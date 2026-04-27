"""add meeting transcripts and segment tables

Revision ID: 007
Revises: 006
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meeting_transcripts",
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("merged_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meeting_id"),
    )
    op.create_table(
        "meeting_transcript_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("uploader_user_id", sa.String(length=36), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("end_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploader_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_meeting_transcript_segments_meeting_id",
        "meeting_transcript_segments",
        ["meeting_id"],
    )
    op.create_index(
        "ix_meeting_transcript_segments_uploader_user_id",
        "meeting_transcript_segments",
        ["uploader_user_id"],
    )
    op.create_index(
        "ix_meeting_transcript_segments_meeting_start",
        "meeting_transcript_segments",
        ["meeting_id", "start_sec"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_meeting_transcript_segments_meeting_start",
        table_name="meeting_transcript_segments",
    )
    op.drop_index(
        "ix_meeting_transcript_segments_uploader_user_id",
        table_name="meeting_transcript_segments",
    )
    op.drop_index("ix_meeting_transcript_segments_meeting_id", table_name="meeting_transcript_segments")
    op.drop_table("meeting_transcript_segments")
    op.drop_table("meeting_transcripts")

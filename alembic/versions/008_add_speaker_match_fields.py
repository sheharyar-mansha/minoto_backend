"""add speaker matching fields on transcript segments

Revision ID: 008
Revises: 007
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meeting_transcript_segments",
        sa.Column("source_uploader_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "meeting_transcript_segments",
        sa.Column("matched_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "meeting_transcript_segments",
        sa.Column("match_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "meeting_transcript_segments",
        sa.Column("match_status", sa.String(length=32), nullable=False, server_default="matched"),
    )
    op.create_index(
        "ix_meeting_transcript_segments_source_uploader_user_id",
        "meeting_transcript_segments",
        ["source_uploader_user_id"],
    )
    op.create_index(
        "ix_meeting_transcript_segments_matched_user_id",
        "meeting_transcript_segments",
        ["matched_user_id"],
    )
    op.create_foreign_key(
        "fk_mts_source_uploader_user_id",
        "meeting_transcript_segments",
        "users",
        ["source_uploader_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_mts_matched_user_id",
        "meeting_transcript_segments",
        "users",
        ["matched_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE meeting_transcript_segments
        SET source_uploader_user_id = uploader_user_id,
            matched_user_id = uploader_user_id
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_mts_matched_user_id", "meeting_transcript_segments", type_="foreignkey")
    op.drop_constraint("fk_mts_source_uploader_user_id", "meeting_transcript_segments", type_="foreignkey")
    op.drop_index(
        "ix_meeting_transcript_segments_matched_user_id",
        table_name="meeting_transcript_segments",
    )
    op.drop_index(
        "ix_meeting_transcript_segments_source_uploader_user_id",
        table_name="meeting_transcript_segments",
    )
    op.drop_column("meeting_transcript_segments", "match_status")
    op.drop_column("meeting_transcript_segments", "match_score")
    op.drop_column("meeting_transcript_segments", "matched_user_id")
    op.drop_column("meeting_transcript_segments", "source_uploader_user_id")

"""add expunge flags to transcript segments

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07

Adds two boolean flags to ``meeting_transcript_segments`` for the spoken
"expunge" command feature (see ``pipeline.expunge``):

    is_command  — the utterance is itself an expunge command (hidden).
    is_expunged — the statement was redacted by a command (shown blue, excluded
                  from the minutes).

Additive and non-destructive: both default to false, so existing rows are
unaffected. Dialect-agnostic (PostgreSQL + SQLite).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meeting_transcript_segments",
        sa.Column("is_command", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "meeting_transcript_segments",
        sa.Column("is_expunged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("meeting_transcript_segments", "is_expunged")
    op.drop_column("meeting_transcript_segments", "is_command")

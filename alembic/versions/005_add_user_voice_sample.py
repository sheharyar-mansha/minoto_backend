"""add user voice sample columns

Revision ID: 005
Revises: 004
Create Date: 2026-04-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("has_voice_sample", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("users", sa.Column("voice_file_path", sa.String(length=1024), nullable=True))
    op.add_column("users", sa.Column("voice_duration_seconds", sa.Integer(), nullable=True))
    op.alter_column("users", "has_voice_sample", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "voice_duration_seconds")
    op.drop_column("users", "voice_file_path")
    op.drop_column("users", "has_voice_sample")

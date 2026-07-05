"""add users.role

Revision ID: 003
Revises: 002
Create Date: 2026-04-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="participant"),
    )
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.execute("UPDATE users SET role = 'participant' WHERE role IS NULL")
    op.alter_column("users", "role", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "role")

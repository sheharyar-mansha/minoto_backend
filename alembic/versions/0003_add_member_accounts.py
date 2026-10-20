"""add read-only login accounts to contacts (members)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18

Adds the optional member-account columns to ``contacts`` for the flag-gated
user-dashboard feature:

    hashed_password   — the member's chosen password (set on first login).
    temp_password     — a one-time random the owner can reveal; cleared once the
                        member sets their own.
    must_set_password — force the "create your password" step on next login.
    password_set_at   — when the member set their own password.

Additive and non-destructive (all nullable / default false). Dialect-agnostic
(PostgreSQL + SQLite).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("hashed_password", sa.String(length=255), nullable=True))
    op.add_column("contacts", sa.Column("temp_password", sa.String(length=64), nullable=True))
    op.add_column(
        "contacts",
        sa.Column("must_set_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("contacts", sa.Column("password_set_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "password_set_at")
    op.drop_column("contacts", "must_set_password")
    op.drop_column("contacts", "temp_password")
    op.drop_column("contacts", "hashed_password")

"""seed default admin user

Revision ID: 004
Revises: 003
Create Date: 2026-04-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from passlib.context import CryptContext

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_ID = "00000000-0000-0000-0000-000000000001"
ADMIN_EMAIL = "admin@minoto.com"
ADMIN_NAME = "Admin"
ADMIN_PASSWORD = "Admin123!"


def upgrade() -> None:
    conn = op.get_bind()
    cols = {c["name"] for c in sa.inspect(conn).get_columns("users")}
    if "role" not in cols:
        conn.execute(
            sa.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'member'"
            )
        )
        conn.execute(
            sa.text("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)")
        )
        conn.execute(sa.text("ALTER TABLE users ALTER COLUMN role DROP DEFAULT"))

    exists = conn.execute(
        sa.text("SELECT 1 FROM users WHERE email = :email LIMIT 1"),
        {"email": ADMIN_EMAIL},
    ).scalar()
    if exists:
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO users (
                id,
                email,
                full_name,
                hashed_password,
                role,
                default_export_format,
                include_timestamps_default
            )
            VALUES (
                :id,
                :email,
                :full_name,
                :hashed_password,
                :role,
                :default_export_format,
                :include_timestamps_default
            )
            """
        ),
        {
            "id": ADMIN_ID,
            "email": ADMIN_EMAIL,
            "full_name": ADMIN_NAME,
            "hashed_password": _pwd.hash(ADMIN_PASSWORD),
            "role": "admin",
            "default_export_format": "pdf",
            "include_timestamps_default": True,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM users WHERE email = :email"),
        {"email": ADMIN_EMAIL},
    )


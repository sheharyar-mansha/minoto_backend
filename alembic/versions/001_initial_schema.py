"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("default_export_format", sa.String(length=32), nullable=False),
        sa.Column("include_timestamps_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=128), nullable=True),
        sa.Column("member_since", sa.Date(), nullable=True),
        sa.Column("saved_to_directory", sa.Boolean(), nullable=False),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("has_voice_sample", sa.Boolean(), nullable=False),
        sa.Column("voice_file_path", sa.String(length=1024), nullable=True),
        sa.Column("voice_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_members_user_id", "members", ["user_id"])
    op.create_index("ix_members_email", "members", ["email"])

    op.create_table(
        "meetings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("meeting_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.String(length=8), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("conducted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meetings_user_id", "meetings", ["user_id"])
    op.create_index("ix_meetings_meeting_date", "meetings", ["meeting_date"])
    op.create_index("ix_meetings_status", "meetings", ["status"])

    op.create_table(
        "meeting_members",
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("is_new_for_meeting", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meeting_id", "member_id"),
    )

    op.create_table(
        "meeting_live_sessions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=False),
        sa.Column("is_paused", sa.Boolean(), nullable=False),
        sa.Column("running_since_ms", sa.BigInteger(), nullable=True),
        sa.Column("total_target_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_meeting_live_sessions_meeting_id", "meeting_live_sessions", ["meeting_id"])


def downgrade() -> None:
    op.drop_index("ix_meeting_live_sessions_meeting_id", table_name="meeting_live_sessions")
    op.drop_table("meeting_live_sessions")
    op.drop_table("meeting_members")
    op.drop_index("ix_meetings_status", table_name="meetings")
    op.drop_index("ix_meetings_meeting_date", table_name="meetings")
    op.drop_index("ix_meetings_user_id", table_name="meetings")
    op.drop_table("meetings")
    op.drop_index("ix_members_email", table_name="members")
    op.drop_index("ix_members_user_id", table_name="members")
    op.drop_table("members")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

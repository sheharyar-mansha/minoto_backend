"""initial single-device schema + seed owner

Revision ID: 0001
Revises: (none)
Create Date: 2026-10-04

Fresh start for the single-device Minoto. Creates every table and seeds the one
owner login (owner@minoto.com / Owner123!). Dialect-agnostic so it runs on both
PostgreSQL (the live DB) and SQLite (tests).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from passlib.context import CryptContext

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("CURRENT_TIMESTAMP")
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

OWNER_ID = "00000000-0000-0000-0000-000000000001"
OWNER_EMAIL = "owner@minoto.com"
OWNER_NAME = "Owner"
OWNER_PASSWORD = "Owner123!"


def upgrade() -> None:
    # --- users (single owner login) ---
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("default_export_format", sa.String(32), nullable=False, server_default=sa.text("'pdf'")),
        sa.Column("include_timestamps_default", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=_NOW),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # --- contacts (global roster + voice enrollment) ---
    op.create_table(
        "contacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("has_voice_sample", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("voice_file_path", sa.String(1024), nullable=True),
        sa.Column("voice_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("voice_embedding_json", sa.Text(), nullable=True),
        sa.Column("voice_recorded_at", sa.DateTime(), nullable=True),
        sa.Column("spoken_name", sa.String(255), nullable=True),
        sa.Column("spoken_name_source", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=_NOW),
    )
    op.create_index("ix_contacts_email", "contacts", ["email"], unique=True)

    # --- meetings ---
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("meeting_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.String(8), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column("conducted_at", sa.DateTime(), nullable=True),
        sa.Column("final_elapsed_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=_NOW),
    )
    op.create_index("ix_meetings_meeting_date", "meetings", ["meeting_date"])
    op.create_index("ix_meetings_scheduled_at", "meetings", ["scheduled_at"])
    op.create_index("ix_meetings_status", "meetings", ["status"])

    # --- meeting_contacts (join) ---
    op.create_table(
        "meeting_contacts",
        sa.Column("meeting_id", sa.String(36), nullable=False),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_NOW),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meeting_id", "contact_id"),
    )

    # --- meeting_recording (one per meeting) ---
    op.create_table(
        "meeting_recording",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("recording_started_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_NOW),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_meeting_recording_meeting_id", "meeting_recording", ["meeting_id"], unique=True)

    # --- meeting_transcripts ---
    op.create_table(
        "meeting_transcripts",
        sa.Column("meeting_id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("pipeline_version", sa.String(32), nullable=True),
        sa.Column("pipeline_stage", sa.String(32), nullable=True),
        sa.Column("merged_text", sa.Text(), nullable=True),
        sa.Column("minutes_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=_NOW),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
    )

    # --- meeting_transcript_segments ---
    op.create_table(
        "meeting_transcript_segments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), nullable=False),
        sa.Column("matched_contact_id", sa.String(36), nullable=True),
        sa.Column("label_name", sa.String(255), nullable=False),
        sa.Column("name_source", sa.String(16), nullable=False, server_default=sa.text("'spoken'")),
        sa.Column("match_status", sa.String(16), nullable=False, server_default=sa.text("'matched'")),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("candidate_contact_ids", sa.Text(), nullable=True),
        sa.Column("is_overlap", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("start_sec", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("end_sec", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("word_timestamps_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_NOW),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_contact_id"], ["contacts.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_meeting_transcript_segments_meeting", "meeting_transcript_segments", ["meeting_id"]
    )
    op.create_index(
        "ix_meeting_transcript_segments_matched_contact",
        "meeting_transcript_segments",
        ["matched_contact_id"],
    )
    op.create_index(
        "ix_meeting_transcript_segments_meeting_start",
        "meeting_transcript_segments",
        ["meeting_id", "start_sec"],
    )

    _seed_owner()


def _seed_owner() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT 1 FROM users WHERE email = :e LIMIT 1"), {"e": OWNER_EMAIL}
    ).scalar()
    if exists:
        return
    conn.execute(
        sa.text(
            """
            INSERT INTO users (id, email, full_name, hashed_password,
                               default_export_format, include_timestamps_default)
            VALUES (:id, :email, :full_name, :hashed_password, :fmt, :ts)
            """
        ),
        {
            "id": OWNER_ID,
            "email": OWNER_EMAIL,
            "full_name": OWNER_NAME,
            "hashed_password": _pwd.hash(OWNER_PASSWORD),
            "fmt": "pdf",
            "ts": True,
        },
    )


def downgrade() -> None:
    op.drop_table("meeting_transcript_segments")
    op.drop_table("meeting_transcripts")
    op.drop_table("meeting_recording")
    op.drop_table("meeting_contacts")
    op.drop_table("meetings")
    op.drop_table("contacts")
    op.drop_table("users")

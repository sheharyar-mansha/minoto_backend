"""v2 schema: participants on users, pipeline columns, drop legacy members tables.

Migrates existing v1 roster data before dropping members / meeting_members:
  meeting_members.member_id -> members.user_id -> meeting_participants.user_id
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _migrate_v1_roster(bind: sa.engine.Connection) -> None:
    """Move meeting roster from members/meeting_members to meeting_participants."""
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "members" not in tables or "meeting_members" not in tables:
        return
    if "meeting_participants" not in tables:
        return

    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                INSERT INTO meeting_participants (meeting_id, user_id, created_at)
                SELECT mm.meeting_id, m.user_id, CURRENT_TIMESTAMP
                FROM meeting_members mm
                JOIN members m ON m.id = mm.member_id
                ON CONFLICT DO NOTHING
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE users u
                SET
                    avatar_url = COALESCE(u.avatar_url, m.avatar_url),
                    has_voice_sample = (u.has_voice_sample OR m.has_voice_sample),
                    voice_file_path = COALESCE(u.voice_file_path, m.voice_file_path),
                    voice_duration_seconds = COALESCE(u.voice_duration_seconds, m.voice_duration_seconds)
                FROM members m
                WHERE m.user_id = u.id
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO meeting_participants (meeting_id, user_id, created_at)
                SELECT mm.meeting_id, m.user_id, CURRENT_TIMESTAMP
                FROM meeting_members mm
                JOIN members m ON m.id = mm.member_id
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE users
                SET avatar_url = COALESCE(
                    avatar_url,
                    (SELECT avatar_url FROM members WHERE members.user_id = users.id LIMIT 1)
                )
                WHERE EXISTS (SELECT 1 FROM members WHERE members.user_id = users.id)
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE users
                SET has_voice_sample = 1
                WHERE has_voice_sample = 0
                  AND EXISTS (
                    SELECT 1 FROM members
                    WHERE members.user_id = users.id AND members.has_voice_sample = 1
                  )
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE users
                SET voice_file_path = COALESCE(
                    voice_file_path,
                    (SELECT voice_file_path FROM members WHERE members.user_id = users.id LIMIT 1)
                )
                WHERE EXISTS (SELECT 1 FROM members WHERE members.user_id = users.id)
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE users
                SET voice_duration_seconds = COALESCE(
                    voice_duration_seconds,
                    (SELECT voice_duration_seconds FROM members WHERE members.user_id = users.id LIMIT 1)
                )
                WHERE EXISTS (SELECT 1 FROM members WHERE members.user_id = users.id)
                """
            )
        )

    if "users" in tables:
        user_cols = {c["name"] for c in insp.get_columns("users")}
        if "role" in user_cols:
            op.execute(
                sa.text("UPDATE users SET role = 'participant' WHERE role = 'member'")
            )


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "meeting_participants" not in tables:
        op.create_table(
            "meeting_participants",
            sa.Column("meeting_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("meeting_id", "user_id"),
        )
        op.create_index("ix_meeting_participants_user_id", "meeting_participants", ["user_id"])

    _migrate_v1_roster(bind)

    if "meeting_device_recordings" in tables:
        rec_cols = {c["name"] for c in insp.get_columns("meeting_device_recordings")}
        if "participant_member_id" in rec_cols:
            with op.batch_alter_table("meeting_device_recordings") as batch:
                batch.drop_column("participant_member_id")

    if "meeting_members" in tables:
        op.drop_table("meeting_members")
    if "members" in tables:
        op.drop_table("members")

    if "users" in tables:
        user_cols = {c["name"] for c in insp.get_columns("users")}
        if "voice_embedding_json" not in user_cols:
            op.add_column("users", sa.Column("voice_embedding_json", sa.Text(), nullable=True))

    if "meeting_device_recordings" in tables:
        rec_cols = {c["name"] for c in insp.get_columns("meeting_device_recordings")}
        if "recording_started_at" not in rec_cols:
            op.add_column(
                "meeting_device_recordings",
                sa.Column("recording_started_at", sa.DateTime(), nullable=True),
            )
        if "recording_ended_at" not in rec_cols:
            op.add_column(
                "meeting_device_recordings",
                sa.Column("recording_ended_at", sa.DateTime(), nullable=True),
            )
        if "device_meta_json" not in rec_cols:
            op.add_column(
                "meeting_device_recordings",
                sa.Column("device_meta_json", sa.Text(), nullable=True),
            )

    if "meeting_transcripts" in tables:
        tx_cols = {c["name"] for c in insp.get_columns("meeting_transcripts")}
        for col, typ in (
            ("pipeline_version", sa.String(length=32)),
            ("pipeline_stage", sa.String(length=32)),
            ("minutes_json", sa.Text()),
        ):
            if col not in tx_cols:
                op.add_column("meeting_transcripts", sa.Column(col, typ, nullable=True))

    if "meeting_transcript_segments" in tables:
        seg_cols = {c["name"] for c in insp.get_columns("meeting_transcript_segments")}
        if "source_recording_id" not in seg_cols:
            op.add_column(
                "meeting_transcript_segments",
                sa.Column("source_recording_id", sa.String(length=36), nullable=True),
            )
        if "word_timestamps_json" not in seg_cols:
            op.add_column(
                "meeting_transcript_segments",
                sa.Column("word_timestamps_json", sa.Text(), nullable=True),
            )


def downgrade() -> None:
    op.drop_table("meeting_participants")

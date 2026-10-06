-- Clear all meeting/contact DATA but keep the schema and the owner login.
-- Usage: psql "<DATABASE_URL>" -f scripts/clear_all_data_postgres.sql
-- (For a full schema reset instead, use scripts/nuclear_wipe_postgres.sql then `alembic upgrade head`.)

TRUNCATE TABLE
    meeting_transcript_segments,
    meeting_transcripts,
    meeting_recording,
    meeting_contacts,
    meetings,
    contacts
RESTART IDENTITY CASCADE;

-- `users` (the single owner) is intentionally left intact so you stay logged in.

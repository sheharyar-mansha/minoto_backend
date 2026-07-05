-- Empty all application rows. Does NOT drop tables or run migrations.
-- Run in pgAdmin / psql on your minoto_dev database.
-- Does NOT re-seed admin — register via app or run nuclear wipe + upgrade head.

BEGIN;

-- Child tables first (TRUNCATE ... CASCADE handles FK order if you list parents too)
TRUNCATE TABLE
  meeting_transcript_segments,
  meeting_transcripts,
  meeting_device_recordings,
  meeting_live_sessions,
  meeting_participants,
  meetings,
  users
RESTART IDENTITY CASCADE;

-- Legacy tables from pre-v2 (no-op if already dropped by migration 010)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'meeting_members') THEN
    EXECUTE 'TRUNCATE TABLE meeting_members RESTART IDENTITY CASCADE';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'members') THEN
    EXECUTE 'TRUNCATE TABLE members RESTART IDENTITY CASCADE';
  END IF;
END $$;

COMMIT;

-- Optional: seed admin again (password: Admin123!)
-- INSERT only if you truncated users and need the default admin back.

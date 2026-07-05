-- OPTIONAL one-way wipe for PostgreSQL (run manually in pgAdmin or psql).
-- Irreversible. Does not delete files under backend/uploads/.
--
-- After this, stamp and rebuild:
--   python -m alembic stamp base
--   python -m alembic upgrade head

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO public;
GRANT ALL ON SCHEMA public TO CURRENT_USER;

# Minoto schema v2 (simplified)

## Roles
- **admin** — seeded manually in DB; creates meetings; picks participants from all users.
- **participant** — default for sign-up; can join meetings they are assigned to.

## Tables
| Table | Purpose |
|-------|---------|
| `users` | Login accounts + profile + voice enrollment + optional embedding JSON |
| `meetings` | Hosted by admin (`user_id`) |
| `meeting_participants` | Many-to-many: meeting ↔ participant user |
| `meeting_live_sessions` | Live timer per admin user |
| `meeting_device_recordings` | Per-device upload + `recording_started_at` / `recording_ended_at` |
| `meeting_transcripts` | Pipeline job status + merged text + `minutes_json` |
| `meeting_transcript_segments` | Speaker-attributed segments + word timestamps JSON |

## Removed
- `members` — directory rows duplicated users; removed.
- `meeting_members` — replaced by `meeting_participants`.

## API (v2)
- `GET /users/accounts` — admin lists participant users (replaces old `/members`).
- `PUT .../participants` body: `{ "user_ids": ["..."] }` (`member_ids` still accepted as alias).
- `participant_member_ids` in meeting detail JSON = participant **user** ids (legacy field name).

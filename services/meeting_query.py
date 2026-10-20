"""Shared query helpers for listing meetings.

Centralises the scope/search/participant/date filters so both the owner's
`GET /meetings` and the member's read-only `GET /members/me/meetings` apply
exactly the same rules.
"""

from datetime import date, datetime

from sqlalchemy import Select

from models.contact import Contact
from models.meeting import Meeting
from models.meeting_transcript import MeetingTranscript

SCOPE_STATUS = {"upcoming": "scheduled", "completed": "completed"}
VALID_SCOPES = ("upcoming", "completed", "all")


def parse_date_query(raw: str | None) -> date | None:
    """Parse a 'YYYY-MM-DD' query value to a date; return None if missing/invalid."""
    if not raw or not raw.strip():
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def apply_meeting_filters(
    stmt: Select,
    *,
    scope: str = "all",
    q: str | None = None,
    search_content: bool = False,
    participant: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Select:
    """Apply the common filters to a `select(Meeting)` statement."""
    if scope in SCOPE_STATUS:
        stmt = stmt.where(Meeting.status == SCOPE_STATUS[scope])
    if q and q.strip():
        term = f"%{q.strip()}%"
        if search_content:
            # Also match the transcript body and the generated minutes (summary,
            # decisions, action items are stored together in minutes_json).
            stmt = stmt.where(
                Meeting.title.ilike(term)
                | Meeting.transcript.has(
                    MeetingTranscript.merged_text.ilike(term)
                    | MeetingTranscript.minutes_json.ilike(term)
                )
            )
        else:
            stmt = stmt.where(Meeting.title.ilike(term))
    # Filter by a participant's name (matches any contact on the meeting).
    if participant and participant.strip():
        stmt = stmt.where(
            Meeting.contacts.any(Contact.name.ilike(f"%{participant.strip()}%"))
        )
    # Date range on the meeting's calendar date. Invalid dates are ignored.
    df = parse_date_query(date_from)
    if df is not None:
        stmt = stmt.where(Meeting.meeting_date >= df)
    dt = parse_date_query(date_to)
    if dt is not None:
        stmt = stmt.where(Meeting.meeting_date <= dt)
    return stmt


def order_meetings(stmt: Select, scope: str) -> Select:
    """Upcoming reads soonest-first; history reads most-recent-first."""
    if scope == "upcoming":
        return stmt.order_by(Meeting.scheduled_at.asc())
    return stmt.order_by(Meeting.scheduled_at.desc())

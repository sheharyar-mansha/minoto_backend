"""ORM models — importing this package registers every table with Base.metadata."""

from models.contact import Contact
from models.meeting import Meeting
from models.meeting_contact import meeting_contacts
from models.meeting_recording import MeetingRecording
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from models.user import User

__all__ = [
    "User",
    "Contact",
    "Meeting",
    "meeting_contacts",
    "MeetingRecording",
    "MeetingTranscript",
    "MeetingTranscriptSegment",
]

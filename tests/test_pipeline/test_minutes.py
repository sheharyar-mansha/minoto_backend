from __future__ import annotations

from pipeline.minutes.gemini_minutes import generate_minutes
from pipeline.types import MinutesDraft, TranscriptSegmentDraft


def _seg(text):
    return TranscriptSegmentDraft(
        start_sec=0.0, end_sec=1.0, text=text,
        speaker_user_id="u1", source_recording_id="rec", source_uploader_user_id="u1",
    )


def test_no_segments_returns_empty_without_network():
    # Must short-circuit before touching the API (no key set in tests).
    assert generate_minutes([], {}, "Standup") == MinutesDraft("", [], [])


def test_all_blank_text_returns_empty_without_network():
    assert generate_minutes([_seg("   "), _seg("")], {}, "Standup") == MinutesDraft("", [], [])

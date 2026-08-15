from __future__ import annotations

from pipeline.assemble.timeline import assemble_timeline, format_merged_text
from pipeline.types import TranscriptSegmentDraft


def _seg(start, end, text, speaker="u1"):
    return TranscriptSegmentDraft(
        start_sec=start, end_sec=end, text=text,
        speaker_user_id=speaker, source_recording_id="rec", source_uploader_user_id="u1",
    )


def test_sorts_by_time_and_drops_empty_text():
    segs = [_seg(10, 11, "second"), _seg(0, 1, "first"), _seg(5, 6, "   ")]
    out = assemble_timeline(segs)
    assert [s.text for s in out] == ["first", "second"]


def test_collapses_adjacent_identical_lines():
    segs = [_seg(0.0, 1.0, "hello"), _seg(1.0, 2.0, "hello")]  # overlapping + identical
    assert len(assemble_timeline(segs)) == 1


def test_keeps_adjacent_different_lines():
    segs = [_seg(0.0, 1.0, "hello"), _seg(1.0, 2.0, "world")]
    assert len(assemble_timeline(segs)) == 2


def test_format_merged_text_timestamp_and_label():
    segs = [_seg(65, 67, "let us begin", "u1")]
    assert format_merged_text(segs, {"u1": "Ali"}) == "[01:05] Ali: let us begin"


def test_format_merged_text_unknown_speaker():
    segs = [_seg(0, 1, "hi", "ghost")]
    assert "Unknown: hi" in format_merged_text(segs, {})

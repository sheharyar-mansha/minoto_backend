from __future__ import annotations

import pytest

from pipeline.align.text_align import (
    align_by_text,
    estimate_offset,
    pick_reference,
    resolve_shared_offsets,
)
from pipeline.types import TranscriptSegmentDraft, WordToken


def _seg(dev, start, end, text):
    return TranscriptSegmentDraft(
        start_sec=start, end_sec=end, text=text,
        speaker_user_id=dev, source_recording_id=dev, source_uploader_user_id=dev,
    )


def _wseg(dev, start, end, words):
    """words: list of (token, word_start) -> a segment carrying word timestamps."""
    toks = [WordToken(word=w, start=ws, end=ws + 0.3) for (w, ws) in words]
    return TranscriptSegmentDraft(
        start_sec=start, end_sec=end, text=" ".join(w for w, _ in words),
        speaker_user_id=dev, source_recording_id=dev, source_uploader_user_id=dev,
        words=toks,
    )


def test_estimate_offset_recovers_known_shift():
    # Phone A's transcript; phone B recorded the same words but started 4s earlier.
    ref = [
        _seg("A", 10.0, 12.0, "we need to identify each and every problem"),
        _seg("A", 20.0, 23.0, "let's try to optimize the application as much as possible"),
        _seg("A", 30.0, 31.5, "as soon as it is optimized our problems are resolved"),
    ]
    shift = 4.0
    other = [_seg("B", s.start_sec - shift, s.end_sec - shift, s.text) for s in ref]
    off = estimate_offset(ref, other)
    assert off is not None
    assert abs(off - shift) < 0.2  # add ~4s to B to line it up with A


def test_estimate_offset_none_without_shared_speech():
    ref = [_seg("A", 0.0, 2.0, "completely different words spoken over here")]
    other = [_seg("B", 0.0, 2.0, "nothing whatsoever in common between them")]
    assert estimate_offset(ref, other) is None


def test_estimate_offset_rejects_outlier_match():
    ref = [
        _seg("A", 10.0, 10.1, "identify each and every problem"),
        _seg("A", 20.0, 20.1, "optimize the whole application today"),
        _seg("A", 30.0, 30.1, "our problems are all resolved now"),
    ]
    other = [
        _seg("B", 7.0, 7.1, "identify each and every problem"),   # delta +3
        _seg("B", 17.0, 17.1, "optimize the whole application today"),  # delta +3
        _seg("B", 27.0, 27.1, "our problems are all resolved now"),     # delta +3
        _seg("B", 50.0, 50.1, "identify each and every problem"),  # coincidental repeat -> outlier
    ]
    off = estimate_offset(ref, other)
    assert off is not None
    assert abs(off - 3.0) < 0.2  # median/inlier average rejects the -40s outlier


def test_align_by_text_reference_is_zero_and_unsure_is_none():
    per_device = {
        "A": [_seg("A", 10.0, 12.0, "let us optimize the whole application today")],
        "B": [_seg("B", 12.0, 14.0, "let us optimize the whole application today")],
    }
    offsets = align_by_text(per_device, "A")
    assert offsets["A"] == 0.0
    assert offsets["B"] is None  # single anchor < ALIGN_MIN_ANCHORS -> not confident


def test_pick_reference_prefers_most_words():
    per_device = {
        "A": [_seg("A", 0, 1, "two words")],
        "B": [_seg("B", 0, 1, "this one has many more spoken words here")],
    }
    assert pick_reference(per_device) == "B"
    assert pick_reference({}) is None


def test_resolve_shared_offsets_aligns_and_normalises_to_zero():
    a = [
        _seg("A", 10.0, 10.1, "identify each and every problem"),
        _seg("A", 20.0, 20.1, "optimize the whole application today"),
        _seg("A", 30.0, 30.1, "our problems are all resolved now"),
    ]
    b = [_seg("B", s.start_sec - 4.0, s.end_sec - 4.0, s.text) for s in a]  # B is 4s ahead
    offsets = resolve_shared_offsets({"A": a, "B": b}, {"A": None, "B": None}, "A")

    aligned = [s.start_sec + offsets["A"] for s in a] + [s.start_sec + offsets["B"] for s in b]
    assert min(aligned) == pytest.approx(0.0, abs=0.2)          # earliest sits at t=0
    assert (a[0].start_sec + offsets["A"]) == pytest.approx(    # same utterance coincides
        b[0].start_sec + offsets["B"], abs=0.3
    )


def test_resolve_shared_offsets_falls_back_to_start_times():
    # No shared words -> use device start-time deltas (B started 3s after A).
    a = [_seg("A", 5.0, 6.0, "alpha bravo charlie delta echo")]
    b = [_seg("B", 5.0, 6.0, "foxtrot golf hotel india juliet")]
    offsets = resolve_shared_offsets({"A": a, "B": b}, {"A": 1000.0, "B": 1003.0}, "A")
    assert (offsets["B"] - offsets["A"]) == pytest.approx(3.0, abs=0.01)


def test_word_timestamps_tighten_offset_beyond_midpoints():
    # Same words; "other" is 3.0s ahead by WORD timing, but its segment spans are wider
    # so midpoints alone would say ~2.5s. Word-level matching must recover ~3.0s.
    ref = [
        _wseg("A", 10.0, 11.0, [("identify", 10.0), ("each", 10.4), ("problem", 10.8)]),
        _wseg("A", 20.0, 21.0, [("optimize", 20.0), ("whole", 20.4), ("application", 20.8)]),
    ]
    other = [
        _wseg("B", 7.0, 9.0, [("identify", 7.0), ("each", 7.4), ("problem", 7.8)]),
        _wseg("B", 17.0, 19.0, [("optimize", 17.0), ("whole", 17.4), ("application", 17.8)]),
    ]
    off = estimate_offset(ref, other)
    assert off is not None
    assert abs(off - 3.0) < 0.15  # midpoint-only would land near 2.5

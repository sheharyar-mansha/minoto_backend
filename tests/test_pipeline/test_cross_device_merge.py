from __future__ import annotations

from pipeline.merge.cross_device import merge_across_devices
from pipeline.types import TranscriptSegmentDraft


def _seg(dev, start, end, text, energy, conf=0.8):
    return TranscriptSegmentDraft(
        start_sec=start,
        end_sec=end,
        text=text,
        speaker_user_id=dev,
        source_recording_id=dev,
        source_uploader_user_id=dev,
        confidence=conf,
        energy=energy,
    )


def test_echo_across_three_phones_collapses_to_nearest_mic():
    # Person A speaks: loud on A's phone, quieter on B's and C's (they sit either side).
    drafts = [
        _seg("A", 10.0, 13.0, "Let's ship it on Friday", energy=0.9),
        _seg("B", 10.1, 13.1, "Let's ship it on Friday", energy=0.2),
        _seg("C", 9.9, 12.9, "let's ship it Friday", energy=0.15),
    ]
    kept = merge_across_devices(drafts)
    assert len(kept) == 1
    assert kept[0].source_recording_id == "A"  # nearest/loudest mic wins


def test_simultaneous_different_speech_is_kept():
    # Genuine crosstalk: A and B talk over each other saying different things.
    drafts = [
        _seg("A", 20.0, 23.0, "I think we should delay the launch", energy=0.9),
        _seg("B", 20.1, 23.2, "No the budget is already approved", energy=0.9),
    ]
    kept = merge_across_devices(drafts)
    assert len(kept) == 2


def test_same_phone_sequential_never_deduped():
    drafts = [
        _seg("A", 0.0, 2.0, "Good morning everyone", energy=0.8),
        _seg("A", 2.5, 5.0, "Let's get started", energy=0.8),
    ]
    kept = merge_across_devices(drafts)
    assert len(kept) == 2

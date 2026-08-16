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


def test_empty_input():
    assert merge_across_devices([]) == []


def test_single_device_keeps_everything():
    # One phone can never echo itself, even with overlapping segments.
    drafts = [
        _seg("A", 0.0, 2.0, "good morning everyone", energy=0.8),
        _seg("A", 1.5, 3.0, "good morning everyone", energy=0.8),
        _seg("A", 4.0, 6.0, "let's begin", energy=0.8),
    ]
    assert len(merge_across_devices(drafts)) == 3


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


def test_garbled_far_mic_is_still_treated_as_echo():
    # Near-identical timing but the far mic mis-heard a couple of words -> still an echo.
    drafts = [
        _seg("A", 5.0, 8.0, "please review the design document today", energy=0.9),
        _seg("B", 5.0, 8.0, "please review the decide document Tuesday", energy=0.2),
    ]
    kept = merge_across_devices(drafts)
    assert len(kept) == 1
    assert kept[0].source_recording_id == "A"


def test_simultaneous_different_speech_is_kept():
    # Genuine crosstalk: A and B talk over each other saying different things.
    drafts = [
        _seg("A", 20.0, 23.0, "I think we should delay the launch", energy=0.9),
        _seg("B", 20.1, 23.2, "No the budget is already approved", energy=0.9),
    ]
    assert len(merge_across_devices(drafts)) == 2


def test_same_phone_sequential_never_deduped():
    drafts = [
        _seg("A", 0.0, 2.0, "Good morning everyone", energy=0.8),
        _seg("A", 2.5, 5.0, "Let's get started", energy=0.8),
    ]
    assert len(merge_across_devices(drafts)) == 2


def test_echo_survives_small_residual_drift():
    # The reported bug: "ali: Hi" printed twice. Even after alignment there can be a
    # small residual offset, so the two "Hi" segments don't perfectly overlap. The
    # time-slack in dedup must still collapse them to one line (kept on Ali's phone).
    drafts = [
        _seg("ali", 5.0, 5.4, "Hi", energy=0.9),
        _seg("amna", 5.9, 6.3, "Hi", energy=0.15),  # ~0.5s gap after alignment
    ]
    kept = merge_across_devices(drafts)
    assert len(kept) == 1
    assert kept[0].source_recording_id == "ali"


def test_relative_energy_beats_raw_mic_gain():
    # B's phone has a much louder mic, so the echo of A's words is louder in RAW terms
    # than on A's own phone. Per-device normalisation must still credit A (the owner),
    # because relative to each phone's own speech, A's words are near-field on A only.
    drafts = [
        _seg("A", 5.0, 5.6, "Hi there team", energy=0.5),           # A's peak is 0.5 -> rel 1.0
        _seg("A", 10.0, 13.0, "A on the roadmap plan", energy=0.5),
        _seg("B", 5.1, 5.7, "Hi there team", energy=0.6),           # louder RAW, but...
        _seg("B", 20.0, 23.0, "B on the budget numbers", energy=3.0),  # B's peak 3.0 -> echo rel 0.2
    ]
    kept = merge_across_devices(drafts)
    assert len(kept) == 3
    hi = [k for k in kept if k.text == "Hi there team"]
    assert len(hi) == 1 and hi[0].source_recording_id == "A"

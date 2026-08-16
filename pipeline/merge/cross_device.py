"""Collapse the same utterance captured by several phones into a single line.

In a Minoto meeting every participant records on their own phone. When person A
speaks, their words land on A's mic (loud, near-field), on B's mic (quieter) and
on C's mic (quieter still). If we transcribed all three we'd print A's sentence
three times.

This module de-duplicates *after* transcription, using a non-maximum-suppression
idea borrowed from object detection:

  1. Score every segment by how likely its device is the one that OWNS the words
     — the speaker's own phone is the nearest mic, so it is both the loudest
     (relative to that phone's own speech) and the clearest to transcribe.
  2. Walk segments best-first and keep each one, unless it is an "echo" of an
     already-kept segment from a *different* device (overlaps in time + says the
     same thing). Echoes are dropped.

Two people genuinely talking at once produce overlapping segments with *different*
text, so they survive as separate lines (that is real crosstalk, not an echo).
"""

from __future__ import annotations

import re

from config.settings import settings
from pipeline.types import TranscriptSegmentDraft

_WORD_RE = re.compile(r"\w+")


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _text_similarity(a: str, b: str) -> float:
    """Jaccard word overlap in [0, 1] — order-insensitive and cheap."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _time_iou(a: TranscriptSegmentDraft, b: TranscriptSegmentDraft) -> float:
    inter = max(0.0, min(a.end_sec, b.end_sec) - max(a.start_sec, b.start_sec))
    if inter <= 0.0:
        return 0.0
    union = (a.end_sec - a.start_sec) + (b.end_sec - b.start_sec) - inter
    return inter / union if union > 0.0 else 0.0


def _time_close(a: TranscriptSegmentDraft, b: TranscriptSegmentDraft, slack: float) -> bool:
    """Overlapping, or separated by no more than `slack` seconds.

    Alignment across independent phones is never perfect, so we can't demand exact
    overlap — a small gap still means "the same moment". `gap` is negative when the
    two segments actually overlap.
    """
    gap = max(a.start_sec, b.start_sec) - min(a.end_sec, b.end_sec)
    return gap <= slack


def _assign_relative_energy(drafts: list[TranscriptSegmentDraft]) -> None:
    """Normalise each segment's loudness by its own device's peak.

    Phones have wildly different mic gains, so raw energy is not comparable across
    devices. Relative energy answers "how loud is this vs. typical speech on THIS
    phone", which tracks proximity — high on the speaker's own phone, low on the
    neighbours' — and IS comparable across devices.
    """
    peaks: dict[str, float] = {}
    for d in drafts:
        peaks[d.source_recording_id] = max(peaks.get(d.source_recording_id, 0.0), d.energy)
    for d in drafts:
        peak = peaks.get(d.source_recording_id, 0.0)
        d.rel_energy = (d.energy / peak) if peak > 1e-9 else 0.0


def _ownership_score(d: TranscriptSegmentDraft) -> float:
    """Higher = more likely this device owns the words. Proximity + ASR clarity."""
    conf = d.confidence if d.confidence is not None else 0.0
    return 0.6 * d.rel_energy + 0.4 * conf


def _is_echo(cand: TranscriptSegmentDraft, kept: TranscriptSegmentDraft) -> bool:
    if cand.source_recording_id == kept.source_recording_id:
        return False  # never dedup two segments from the same phone
    # Same moment in time (allowing for imperfect cross-device alignment)?
    if not _time_close(cand, kept, settings.DEDUP_TIME_SLACK_SEC):
        return False
    sim = _text_similarity(cand.text, kept.text)
    if sim >= settings.DEDUP_MIN_TEXT_SIM:
        return True  # same moment, same words -> clearly the same utterance
    # Near-identical timing but the far mic garbled the words: still an echo,
    # as long as the texts aren't outright different (which would be crosstalk).
    if _time_iou(cand, kept) >= settings.DEDUP_HIGH_TIME_IOU and sim >= settings.DEDUP_LOW_TEXT_SIM:
        return True
    return False


def merge_across_devices(
    drafts: list[TranscriptSegmentDraft],
) -> list[TranscriptSegmentDraft]:
    """Return one segment per real utterance, keeping the nearest/clearest mic."""
    if not drafts:
        return []
    _assign_relative_energy(drafts)
    kept: list[TranscriptSegmentDraft] = []
    for cand in sorted(drafts, key=_ownership_score, reverse=True):  # best mic first
        if any(_is_echo(cand, k) for k in kept):
            continue
        kept.append(cand)
    kept.sort(key=lambda d: (d.start_sec, d.end_sec))
    return kept

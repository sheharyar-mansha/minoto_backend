"""Align independent phones in time using the WORDS they both recorded.

The problem: every participant records on their own phone, and those phones share
no clock. To merge their transcripts onto one timeline we need each phone's time
offset. Cross-correlating the raw audio (GCC-PHAT) is unreliable here because each
phone is near-field to a *different* speaker, so the waveforms are dominated by
different content and barely correlate.

The insight: the phones DO capture the same spoken words (loud on the speaker's
phone, faint on the others). So the transcripts share phrases. If phrase "let's
optimize the application" sits at 20.0s on phone A and 24.0s on phone B, then phone
B runs 4s behind A. We collect every such shared-phrase match and take a robust
(outlier-resistant) average of the time gaps -> the offset.

This is exactly the signal GCC-PHAT lacks, and it degrades gracefully: if two
phones share too little speech to be sure, we return None and the caller falls back
to device start-time deltas.
"""

from __future__ import annotations

import re

from config.settings import settings
from pipeline.types import TranscriptSegmentDraft

_WORD_RE = re.compile(r"\w+")


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _midpoint(seg: TranscriptSegmentDraft) -> float:
    return 0.5 * (seg.start_sec + seg.end_sec)


def _norm_word(raw: str) -> str:
    found = _WORD_RE.findall(raw.lower())
    return found[0] if found else ""


def _unique_word_starts(seg: TranscriptSegmentDraft) -> dict[str, float]:
    """Start time of each word that appears exactly once in this segment.

    Restricting to unique words gives unambiguous cross-device word matches.
    """
    counts: dict[str, int] = {}
    starts: dict[str, float] = {}
    for w in seg.words:
        key = _norm_word(w.word)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        starts[key] = w.start
    return {k: starts[k] for k, c in counts.items() if c == 1}


def _word_level_delta(a: TranscriptSegmentDraft, b: TranscriptSegmentDraft) -> float | None:
    """Offset from matching individual word timestamps — tighter than segment midpoints.

    Two phones segment the same speech differently, so their midpoints don't line up on
    the same instant. Matching shared words (which carry their own timestamps) removes
    that bias. Returns None when word timestamps are absent so the caller can fall back.
    """
    sa, sb = _unique_word_starts(a), _unique_word_starts(b)
    shared = set(sa) & set(sb)
    if not shared:
        return None
    return sum(sa[w] - sb[w] for w in shared) / len(shared)


def estimate_offset(
    reference: list[TranscriptSegmentDraft],
    other: list[TranscriptSegmentDraft],
) -> float | None:
    """Seconds to ADD to `other`'s timestamps so they line up with `reference`.

    Returns None when the two devices share too little distinctive speech to trust.
    """
    if not reference or not other:
        return None
    min_sim = settings.ALIGN_MIN_ANCHOR_SIM
    min_words = settings.ALIGN_MIN_ANCHOR_WORDS

    # Pre-tokenise the reference once; skip phrases too short to be distinctive.
    ref_tok: list[tuple[set[str], TranscriptSegmentDraft]] = []
    for s in reference:
        toks = set(_tokens(s.text))
        if len(toks) >= min_words:
            ref_tok.append((toks, s))
    if not ref_tok:
        return None

    deltas: list[float] = []
    for s in other:
        ot = set(_tokens(s.text))
        if len(ot) < min_words:
            continue
        best_sim, best_ref = 0.0, None
        for rset, rs in ref_tok:
            inter = len(ot & rset)
            if inter == 0:
                continue
            sim = inter / len(ot | rset)  # Jaccard word overlap
            if sim > best_sim:
                best_sim, best_ref = sim, rs
        if best_ref is not None and best_sim >= min_sim:
            # Prefer word-level timing; fall back to midpoints when words are absent.
            delta = _word_level_delta(best_ref, s)
            if delta is None:
                delta = _midpoint(best_ref) - _midpoint(s)
            deltas.append(delta)

    if len(deltas) < settings.ALIGN_MIN_ANCHORS:
        return None

    # Robust central value: median, then average only the deltas clustered around it
    # (a phrase said twice, or a coincidental match, becomes an outlier we discard).
    deltas.sort()
    median = deltas[len(deltas) // 2]
    band = settings.ALIGN_INLIER_BAND_SEC
    inliers = [d for d in deltas if abs(d - median) <= band]
    return sum(inliers) / len(inliers) if inliers else median


def align_by_text(
    per_device: dict[str, list[TranscriptSegmentDraft]],
    reference_id: str,
) -> dict[str, float | None]:
    """Offset (seconds to add) per device to align it with the reference device.

    The reference maps to 0.0; any device we can't confidently align maps to None so
    the caller can fall back to device start-times.
    """
    offsets: dict[str, float | None] = {reference_id: 0.0}
    ref_segs = per_device.get(reference_id, [])
    for dev_id, segs in per_device.items():
        if dev_id == reference_id:
            continue
        offsets[dev_id] = estimate_offset(ref_segs, segs)
    return offsets


def pick_reference(per_device: dict[str, list[TranscriptSegmentDraft]]) -> str | None:
    """The device with the most transcribed words is the best alignment anchor."""
    if not per_device:
        return None
    return max(per_device, key=lambda c: sum(len(s.text.split()) for s in per_device[c]))


def resolve_shared_offsets(
    per_device: dict[str, list[TranscriptSegmentDraft]],
    started_at: dict[str, float | None],
    reference_id: str,
) -> dict[str, float]:
    """Final local->shared offset per device.

    Aligns on shared words where possible, falls back to device start-time deltas,
    then shifts everything so the earliest segment sits at t=0. The returned offset
    is what you ADD to each device's local timestamps to place them on one timeline.
    """
    text_offsets = align_by_text(per_device, reference_id)
    raw: dict[str, float] = {}
    for cid in per_device:
        off = text_offsets.get(cid)
        if off is None:  # too little shared speech -> use device start-times
            sd = started_at.get(cid)
            sr0 = started_at.get(reference_id)
            off = (sd - sr0) if (sd is not None and sr0 is not None) else 0.0
        raw[cid] = off
    min_shared = min(
        (d.start_sec + raw[cid] for cid, segs in per_device.items() for d in segs),
        default=0.0,
    )
    return {cid: raw[cid] - min_shared for cid in per_device}

"""Stitch ASR words and diarized turns into one-speaker transcript segments.

The ASR and diarization run independently, so we reconcile them at the *word*
level: each transcribed word is attributed to the diarized turn it overlaps most
(or, if it overlaps none, the nearest turn by midpoint). Consecutive words sharing
a speaker are then grouped into a single segment. This gives clean speaker turns
even when one ASR segment spans a speaker change.

All functions here are pure (lists/dicts in, lists/dicts out) so they can be
reasoned about and tested without audio.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

__all__ = [
    "flatten_words",
    "assign_words_to_turns",
    "group_words_into_segments",
    "format_merged_text",
    "format_timestamp",
]


def flatten_words(asr_segments: list[dict]) -> list[dict]:
    """Flatten ASR segments into an ordered word stream.

    Each word carries its parent segment's confidence/no_speech so grouped
    segments can report a sensible aggregate confidence. Words without timestamps
    (rare) are skipped.
    """
    words: list[dict] = []
    for seg in asr_segments:
        seg_conf = float(seg.get("confidence") or 0.0)
        for w in seg.get("words") or []:
            if w.get("start") is None or w.get("end") is None:
                continue
            words.append(
                {
                    "word": w["word"],
                    "start": float(w["start"]),
                    "end": float(w["end"]),
                    "probability": float(w.get("probability") or 0.0),
                    "seg_confidence": seg_conf,
                }
            )
    words.sort(key=lambda w: (w["start"], w["end"]))
    return words


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_words_to_turns(words: list[dict], turns: list[dict]) -> list[dict]:
    """Attach ``label`` and ``is_overlap`` to each word from the best-matching turn.

    Best match = maximum temporal overlap; ties/no-overlap fall back to the turn
    whose midpoint is nearest the word's midpoint. With no turns, every word is
    labelled ``None`` (caller treats as a single unknown speaker).
    """
    if not turns:
        for w in words:
            w["label"] = None
            w["is_overlap"] = False
        return words

    for w in words:
        w_mid = (w["start"] + w["end"]) / 2.0
        best_turn = None
        best_overlap = 0.0
        for t in turns:
            ov = _overlap(w["start"], w["end"], t["start"], t["end"])
            if ov > best_overlap:
                best_overlap = ov
                best_turn = t

        if best_turn is None:
            # No overlap with any turn — snap to nearest by midpoint.
            best_turn = min(
                turns,
                key=lambda t: abs(((t["start"] + t["end"]) / 2.0) - w_mid),
            )

        w["label"] = best_turn["speaker_label"]
        w["is_overlap"] = bool(best_turn.get("is_overlap", False))
    return words


def group_words_into_segments(words: list[dict]) -> list[dict]:
    """Group a labelled word stream into consecutive one-speaker segments.

    Returns ``[{speaker_label, start, end, text, confidence, is_overlap, words}]``.
    """
    segments: list[dict] = []
    current: dict | None = None

    for w in words:
        label = w.get("label")
        if current is None or current["speaker_label"] != label:
            if current is not None:
                segments.append(_finalize(current))
            current = {
                "speaker_label": label,
                "start": w["start"],
                "end": w["end"],
                "words": [w],
                "is_overlap": bool(w.get("is_overlap", False)),
            }
        else:
            current["end"] = w["end"]
            current["words"].append(w)
            current["is_overlap"] = current["is_overlap"] or bool(w.get("is_overlap", False))

    if current is not None:
        segments.append(_finalize(current))
    return segments


def _finalize(seg: dict) -> dict:
    words = seg["words"]
    text = " ".join(w["word"].strip() for w in words).strip()
    # Collapse the double spaces whisper leaves around leading-space word tokens.
    text = " ".join(text.split())
    confs = [w["seg_confidence"] for w in words if w.get("seg_confidence")]
    confidence = sum(confs) / len(confs) if confs else None
    return {
        "speaker_label": seg["speaker_label"],
        "start": float(seg["start"]),
        "end": float(seg["end"]),
        "text": text,
        "confidence": confidence,
        "is_overlap": bool(seg["is_overlap"]),
        "words": words,
    }


def format_timestamp(seconds: float) -> str:
    """Format a second offset as ``mm:ss`` (or ``h:mm:ss`` past an hour)."""
    total = max(0, int(round(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_merged_text(segments: list[dict]) -> str:
    """Render segments as ``[mm:ss] Name: text`` lines.

    Each segment must carry ``start`` (float), ``label_name`` (str) and ``text``.
    """
    lines = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{format_timestamp(seg['start'])}] {seg['label_name']}: {text}")
    return "\n".join(lines)

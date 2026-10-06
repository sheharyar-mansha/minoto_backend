"""Detect and apply spoken "expunge" commands in a transcript.

During a meeting a participant can redact a statement by saying, out loud:

    "expunge my last statement"             -> redacts the speaker's own most
                                               recent prior statement.
    "expunge last statement of <name>"      -> redacts the most recent prior
                                               statement by the named participant.

Effect on the transcript:
    * the command utterance itself is marked ``is_command`` — hidden from the
      transcript and excluded from the minutes (it is control, not content).
    * the targeted statement is marked ``is_expunged`` — it STAYS in the
      transcript (the app renders it blue) but is excluded from the minutes.

This module is a pure function over an ordered list of segment dicts, so it can
be unit-tested without any audio. Resolving "my"/"<name>" relies on speaker
attribution (diarization + identification); on an ASR-only transcript every
segment shares one speaker, so "my" still works and a named target simply finds
no match (the command is noted, nothing is redacted).
"""

from __future__ import annotations

import re

__all__ = ["apply_expunge_commands", "is_expunge_command"]

# "expunge my last statement"
_MY_RE = re.compile(r"\bexpunge\s+my\s+last\s+statement\b", re.IGNORECASE)
# "expunge [the] last statement of <name...>" — capture a generous trailing run;
# the first name word is what actually resolves the speaker.
_NAMED_RE = re.compile(
    r"\bexpunge\s+(?:the\s+)?last\s+statement\s+of\s+([A-Za-z][A-Za-z '\-]*)",
    re.IGNORECASE,
)


def _norm(token: str) -> str:
    """Lowercase, letters-only, so 'Daniel.' and 'daniel' compare equal."""
    return re.sub(r"[^a-z]", "", (token or "").lower())


def is_expunge_command(text: str) -> bool:
    """True when ``text`` contains a recognised expunge command."""
    text = text or ""
    return bool(_MY_RE.search(text) or _NAMED_RE.search(text))


def _name_tokens(names) -> set[str]:
    """Normalised word tokens for a speaker, e.g. 'Sara Khan' -> {'sara','khan'}."""
    toks: set[str] = set()
    for nm in names or []:
        for part in re.findall(r"[A-Za-z']+", nm or ""):
            n = _norm(part)
            if n:
                toks.add(n)
    return toks


def _match_named_speaker(raw_name: str, speaker_names: dict) -> object | None:
    """Return the speaker_label whose name best matches the spoken ``raw_name``.

    Uses the first spoken word (the given name) as the discriminator: a speaker
    matches when one of their name tokens equals it, or begins with it (so
    "Daniel" resolves "Daniel Khan"). Exact matches win over prefix matches.
    """
    words = re.findall(r"[A-Za-z']+", raw_name or "")
    if not words:
        return None
    want = _norm(words[0])
    if not want:
        return None
    for label, toks in speaker_names.items():
        if want in toks:
            return label
    for label, toks in speaker_names.items():
        if any(tok.startswith(want) for tok in toks):
            return label
    return None


def apply_expunge_commands(segments: list[dict]) -> list[dict]:
    """Annotate each segment with ``is_command`` and ``is_expunged`` in place.

    ``segments`` must be ordered by time. Each dict needs:
        speaker_label : hashable speaker id (``None`` for ASR-only / single speaker)
        names         : iterable of name strings for that speaker ([] when unknown)
        text          : the spoken text

    Returns the same list for convenience.
    """
    # Map each speaker to their normalised name tokens (collected across segments).
    speaker_names: dict = {}
    for seg in segments:
        label = seg.get("speaker_label")
        speaker_names.setdefault(label, set()).update(_name_tokens(seg.get("names")))

    for seg in segments:
        seg.setdefault("is_command", False)
        seg.setdefault("is_expunged", False)

    for i, seg in enumerate(segments):
        text = seg.get("text") or ""
        if _MY_RE.search(text):
            seg["is_command"] = True
            target_label = seg.get("speaker_label")
            has_target = True  # "my" always targets the speaker's own line
        else:
            m = _NAMED_RE.search(text)
            if not m:
                continue
            seg["is_command"] = True
            target_label = _match_named_speaker(m.group(1), speaker_names)
            has_target = target_label is not None

        if not has_target:
            continue  # named speaker not found — command noted, nothing to redact

        # Walk backwards for the most recent prior statement by the target
        # speaker that is neither a command nor already expunged.
        for j in range(i - 1, -1, -1):
            prev = segments[j]
            if prev.get("is_command") or prev.get("is_expunged"):
                continue
            if prev.get("speaker_label") == target_label:
                prev["is_expunged"] = True
                break

    return segments

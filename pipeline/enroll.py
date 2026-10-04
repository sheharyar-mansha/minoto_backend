"""Contact voice enrollment.

When a contact records their guided intro ("Hi, my name is ___") we extract two
things that are reused across every meeting:

  1. a 512-dim pyannote/embedding voiceprint (``embedding_json``) used to IDENTIFY
     the person in meeting recordings, and
  2. their spoken name — the name they actually say — used to label them in the
     transcript (falling back to the roster name when we can't extract it).

Name extraction is a pure, ordered regex over the opening of the intro; if nothing
matches and a Gemini key is configured, a strict-JSON LLM fallback is tried.

Enrollment is deliberately resilient: any failure (bad audio, model/token missing)
yields ``embedding_json=None`` rather than raising, so the API still saves the
member with ``has_voice_sample=True``.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx

from config.settings import settings

log = logging.getLogger(__name__)

__all__ = ["enroll_contact_voice", "extract_spoken_name"]

# A name is 1-2 capitalised-ish word tokens (we Title-case the output anyway).
_NAME = r"([A-Za-z][A-Za-z'’\-]*(?:\s+[A-Za-z][A-Za-z'’\-]*)?)"

# Ordered openers, highest-confidence first. Matched case-insensitively.
_NAME_PATTERNS = [
    re.compile(r"\bmy name is\s+" + _NAME, re.IGNORECASE),
    re.compile(r"\bi\s+am\s+" + _NAME, re.IGNORECASE),
    re.compile(r"\bi['’]?m\s+" + _NAME, re.IGNORECASE),
    re.compile(r"\bthis is\s+" + _NAME, re.IGNORECASE),
]

# First-token guard: words that follow "I'm"/"I am" but are clearly not names,
# so "I'm really happy" / "I am going to..." don't produce a bogus name.
_NOT_NAME_FIRST_TOKEN = {
    "a", "an", "the", "going", "not", "so", "very", "really", "just", "here",
    "from", "at", "in", "on", "with", "glad", "happy", "excited", "pleased",
    "sorry", "about", "doing", "good", "fine", "ready", "calling", "speaking",
}

# Connectives/prepositions that may be captured right after the name but are not
# part of it (e.g. "Omar from marketing" -> "Omar").
_STOP_CONTINUE_TOKENS = {
    "from", "and", "the", "of", "at", "in", "on", "with", "who", "here",
    "nice", "speaking", "calling", "today", "a", "an",
}

# Only scan the opening of the intro — names come first.
_OPENING_CHARS = 240


def _clean_name(raw: str) -> str | None:
    tokens = [t.strip(".,!?;:'\"-’") for t in raw.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return None
    if tokens[0].lower() in _NOT_NAME_FIRST_TOKEN:
        return None
    # Keep the first token; include a second only if it's a plausible name part
    # (not a connective like "from"/"and"/"the" that trails the captured name).
    kept = [tokens[0]]
    if len(tokens) > 1 and tokens[1].lower() not in _STOP_CONTINUE_TOKENS:
        kept.append(tokens[1])
    return " ".join(t[:1].upper() + t[1:].lower() for t in kept)


def extract_spoken_name(transcript_text: str) -> tuple[str | None, str | None]:
    """Pure name extractor over the intro's opening.

    Returns ``(name, source)`` where source is ``'intro_regex'`` on a hit, else
    ``(None, None)`` (the caller may then try the Gemini fallback).
    """
    if not transcript_text:
        return None, None
    opening = transcript_text.strip()[:_OPENING_CHARS]
    for pattern in _NAME_PATTERNS:
        m = pattern.search(opening)
        if not m:
            continue
        name = _clean_name(m.group(1))
        if name:
            return name, "intro_regex"
    return None, None


def _extract_spoken_name_gemini(transcript_text: str) -> str | None:
    """LLM fallback — strict JSON ``{"name": string|null}``. None on any failure."""
    if not settings.GEMINI_API_KEY or not (transcript_text or "").strip():
        return None
    prompt = (
        "Extract the speaker's own name from this self-introduction. "
        'Respond as strict JSON only: {"name": string|null}. '
        "Use null if no name is stated. Return just the person's name (first and "
        "optionally last), with no titles or extra words.\n\n"
        f"Introduction:\n{transcript_text.strip()[:1000]}"
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        name = parsed.get("name")
        if not name:
            return None
        return _clean_name(str(name))
    except Exception:
        log.warning("Gemini name extraction failed; leaving spoken_name empty.", exc_info=True)
        return None


def enroll_contact_voice(audio_path: Path | str) -> dict:
    """Compute enrollment data from a contact's recorded voice intro.

    Returns a dict with ``embedding_json`` (JSON 512-dim vector | None),
    ``spoken_name`` (str | None) and ``spoken_name_source``
    (``'intro_regex'`` | ``'intro_gemini'`` | None). Never raises — on failure the
    member is still saved (with ``has_voice_sample`` set by the API).
    """
    path = Path(audio_path)
    result: dict = {"embedding_json": None, "spoken_name": None, "spoken_name_source": None}

    # Decode once; reuse for both embedding and transcription.
    audio = None
    sr = 16000
    try:
        from pipeline.audio_io import load_mono_wav

        audio, sr = load_mono_wav(path)
    except Exception:
        log.exception("Enrollment: could not decode %s", path)

    # 1) Voiceprint embedding (512-dim pyannote/embedding).
    if audio is not None and audio.size > 0:
        try:
            from pipeline.speaker.backends import (
                get_embedding_backend,
                serialize_embedding,
            )

            backend = get_embedding_backend()
            # A usable voiceprint needs at least ~0.5s of audio.
            if audio.size >= int(sr * 0.5):
                vec = backend.embed_waveform(audio, sr)
                if vec is not None:
                    result["embedding_json"] = serialize_embedding(vec)
            else:
                log.warning("Enrollment: intro too short (%d samples) for a voiceprint.", audio.size)
        except Exception:
            log.exception("Enrollment: embedding failed for %s", path)

    # 2) Spoken name from the transcribed intro (regex, then optional Gemini).
    if audio is not None and audio.size > 0:
        try:
            from pipeline.transcribe import transcribe_file

            segments = transcribe_file(audio)
            intro_text = " ".join(s["text"] for s in segments).strip()
            name, source = extract_spoken_name(intro_text)
            if not name and settings.GEMINI_API_KEY:
                gemini_name = _extract_spoken_name_gemini(intro_text)
                if gemini_name:
                    name, source = gemini_name, "intro_gemini"
            result["spoken_name"] = name
            result["spoken_name_source"] = source
        except Exception:
            log.exception("Enrollment: name extraction failed for %s", path)

    return result

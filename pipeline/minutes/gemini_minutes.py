"""Structured meeting minutes via Google Gemini.

Kept for Phase 3. The transcript pipeline calls `generate_minutes` with the
attributed transcript segments once real transcription exists. The segment type
is duck-typed: any object exposing `.text` (str) and `.speaker_name` (str) works,
so this module stays decoupled from the pipeline's internal dataclasses.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from config.settings import settings

log = logging.getLogger(__name__)


class MinutesSegment(Protocol):
    """A single attributed transcript line (duck-typed)."""

    text: str
    speaker_name: str


@dataclass
class MinutesDraft:
    summary: str = ""
    decisions: list[str] = field(default_factory=list)
    action_items: list[dict] = field(default_factory=list)


def generate_minutes(segments: list[MinutesSegment], meeting_title: str) -> MinutesDraft:
    """Summarize a transcript into structured minutes.

    Raises RuntimeError if GEMINI_API_KEY is unset. Returns empty minutes when
    there is no speech (without spending a network call on nothing).
    """
    if not segments or not any((seg.text or "").strip() for seg in segments):
        return MinutesDraft()
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set — cannot generate structured minutes.")

    transcript_lines = [
        f"{getattr(seg, 'speaker_name', None) or 'Unknown'}: {seg.text.strip()}"
        for seg in segments
        if (seg.text or "").strip()
    ]

    prompt = (
        "You produce meeting minutes as strict JSON only.\n"
        'Schema: {"summary": string, "decisions": string[], '
        '"action_items": [{"assignee": string, "task": string, "due_date": string|null}]}\n'
        f"Meeting title: {meeting_title}\n\nTranscript:\n"
        + "\n".join(transcript_lines)
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(text)
    return MinutesDraft(
        summary=str(parsed.get("summary") or ""),
        decisions=[str(x) for x in parsed.get("decisions") or []],
        action_items=list(parsed.get("action_items") or []),
    )

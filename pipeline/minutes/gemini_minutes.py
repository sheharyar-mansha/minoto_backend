from __future__ import annotations

import json
import logging

import httpx

from config.settings import settings
from pipeline.types import MinutesDraft, TranscriptSegmentDraft

log = logging.getLogger(__name__)


def generate_minutes(
    segments: list[TranscriptSegmentDraft],
    labels: dict[str, str],
    meeting_title: str,
) -> MinutesDraft:
    # No speech -> empty minutes, without spending a network call on nothing.
    if not segments or not any(seg.text.strip() for seg in segments):
        return MinutesDraft(summary="", decisions=[], action_items=[])
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set — cannot generate structured minutes.")

    transcript_lines = []
    for seg in segments:
        name = labels.get(seg.speaker_user_id, "Unknown")
        transcript_lines.append(f"{name}: {seg.text.strip()}")

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

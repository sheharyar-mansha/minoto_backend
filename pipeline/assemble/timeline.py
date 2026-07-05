from __future__ import annotations

from pipeline.types import TranscriptSegmentDraft


def assemble_timeline(segments: list[TranscriptSegmentDraft]) -> list[TranscriptSegmentDraft]:
    merged = sorted(segments, key=lambda s: (s.start_sec, s.end_sec))
    out: list[TranscriptSegmentDraft] = []
    for seg in merged:
        if not seg.text.strip():
            continue
        if out and seg.start_sec <= out[-1].end_sec + 0.05:
            if seg.text.strip() == out[-1].text.strip():
                continue
        out.append(seg)
    return out


def format_merged_text(segments: list[TranscriptSegmentDraft], labels: dict[str, str]) -> str:
    lines: list[str] = []
    for seg in segments:
        name = labels.get(seg.speaker_user_id, "Unknown")
        mm = int(seg.start_sec // 60)
        ss = int(seg.start_sec % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {name}: {seg.text.strip()}")
    return "\n".join(lines)

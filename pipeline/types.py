from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChannelRecording:
    recording_id: str
    uploader_user_id: str
    path: Path
    duration_sec: float
    offset_sec: float = 0.0
    recording_started_at: float | None = None


@dataclass
class WordToken:
    word: str
    start: float
    end: float


@dataclass
class TranscriptSegmentDraft:
    start_sec: float
    end_sec: float
    text: str
    speaker_user_id: str
    source_recording_id: str
    source_uploader_user_id: str
    confidence: float | None = None
    match_score: float | None = None
    match_status: str = "matched"
    words: list[WordToken] = field(default_factory=list)
    # Loudness of this segment on its own device (proximity proxy for cross-device dedup).
    energy: float = 0.0
    # energy normalised by the device's own peak, so mic-gain differences don't skew the pick.
    rel_energy: float = 0.0
    # Whisper's probability the segment is actually silence (used to drop hallucinations).
    no_speech_prob: float | None = None


@dataclass
class MinutesDraft:
    summary: str
    decisions: list[str]
    action_items: list[dict]

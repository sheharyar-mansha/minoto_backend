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
class SpeechRegion:
    channel_id: str
    uploader_user_id: str
    start_sec: float
    end_sec: float
    energy: float = 0.0


@dataclass
class SelectedRegion:
    channel_id: str
    uploader_user_id: str
    start_sec: float
    end_sec: float
    score: float


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


@dataclass
class MinutesDraft:
    summary: str
    decisions: list[str]
    action_items: list[dict]

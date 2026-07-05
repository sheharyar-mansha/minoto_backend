from __future__ import annotations

from pathlib import Path

from pipeline.types import TranscriptSegmentDraft, WordToken


def transcribe_slice(
    audio_path: Path,
    start_sec: float,
    end_sec: float,
    recording_id: str,
    uploader_user_id: str,
) -> TranscriptSegmentDraft | None:
    """Transcribe a time slice using configured ASR backend."""
    from pipeline.asr.backends import get_asr_backend

    backend = get_asr_backend()
    return backend.transcribe_slice(
        audio_path=audio_path,
        start_sec=start_sec,
        end_sec=end_sec,
        recording_id=recording_id,
        uploader_user_id=uploader_user_id,
    )


def empty_draft(
    start_sec: float,
    end_sec: float,
    recording_id: str,
    uploader_user_id: str,
) -> TranscriptSegmentDraft:
    return TranscriptSegmentDraft(
        start_sec=start_sec,
        end_sec=end_sec,
        text="",
        speaker_user_id=uploader_user_id,
        source_recording_id=recording_id,
        source_uploader_user_id=uploader_user_id,
        words=[],
    )

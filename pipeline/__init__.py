"""Single-device meeting pipeline.

The full ML pipeline (Phase 3):
  - `pipeline.enroll.enroll_contact_voice` — pyannote/embedding voiceprint (512-d)
    + spoken-name extraction (regex, optional Gemini) from a contact's intro.
  - `pipeline.runner.generate_meeting_transcript` — diarize (pyannote) -> re-embed
    clusters & identify enrolled contacts (closed-set Hungarian matching) ->
    transcribe (faster-whisper) -> assign words to speakers -> persist segments
    + merged text -> structured minutes (Gemini).

Engine map (see `pipeline.device`): pyannote runs on cpu/mps/cuda; faster-whisper
(CTranslate2) has no Metal backend, so on a Mac it runs cpu/int8 while pyannote
can use mps. The pipeline degrades to ASR-only when diarization is unavailable.
"""

from config.settings import settings

PIPELINE_VERSION = settings.PIPELINE_VERSION

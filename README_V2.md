# MoM backend v2

Shared API for mobile + web.

## Setup (one command for Python deps)

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Optional **NVIDIA GPU** (CUDA 12.4), after the above:

```bash
pip install -r requirements-gpu.txt
```

Copy env, migrate, run:

```bash
copy .env.example .env   # Windows — edit DATABASE_URL + API keys
python -m alembic upgrade head
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### What `pip install -r requirements.txt` includes

| Area | Packages |
|------|----------|
| API | FastAPI, Uvicorn, SQLAlchemy, Alembic, JWT, etc. |
| ASR | faster-whisper, torch, torchaudio |
| Speaker ID | pyannote.audio, huggingface-hub |
| Audio I/O | numpy, scipy, soundfile, **imageio-ffmpeg** (bundled ffmpeg) |
| Minutes | httpx (calls Gemini API — key in `.env`) |
| Tests | pytest |

### What you still configure in `.env` (not pip)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `PYANNOTE_AUTH_TOKEN` | Hugging Face token ([pyannote/embedding](https://huggingface.co/pyannote/embedding) terms accepted) |
| `GEMINI_API_KEY` | Google AI Studio — structured meeting minutes |
| `SECRET_KEY` | JWT signing (optional in local dev) |

See `.env.example` for the full list.

## Schema

- `users` — roles: `admin` (seed in DB) | `participant` (sign-up default)
- `meeting_participants` — users invited to a meeting
- No separate `members` table; use `GET /users/accounts` for the participant directory

## Pipeline (`pipeline/runner.py`)

1. GCC-PHAT alignment
2. Energy VAD per channel
3. Near-field channel selection (structural dedup)
4. ASR on winning slices only (`ASR_BACKEND=faster_whisper`)
5. Speaker verify + device prior (`EMBEDDING_BACKEND=pyannote`, `PYANNOTE_AUTH_TOKEN`)
6. Assembly + Gemini minutes (`GEMINI_API_KEY` required for minutes; transcript completes without)

See [docs/SCHEMA_V2.md](docs/SCHEMA_V2.md).

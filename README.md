# MOM backend (Python API)

FastAPI service for Minoto: auth, members, meetings, uploads (voice/avatars), and related JSON APIs. This repository is the **backend only**; frontends (e.g. mobile or web) live in separate projects.

- **Default branch:** **`mom-be`** (not `main`).
- **Contributing:** open a **feature branch** from `mom-be` and a **pull request** into **`mom-be`**. Do **not** push commits directly to **`mom-be`**.

---

## Contents

1. [What you need](#what-you-need)
2. [Quick start (PostgreSQL, recommended)](#quick-start-postgresql-recommended)
3. [Quick start (SQLite)](#quick-start-sqlite)
4. [Virtual environment (Windows)](#virtual-environment-windows)
5. [Environment variables (`.env`)](#environment-variables-env)
6. [Database & migrations](#database--migrations)
7. [Run the server](#run-the-server)
8. [Verify it works](#verify-it-works)
9. [API reference](#api-reference)
10. [PostgreSQL notes](#postgresql-notes)
11. [Project layout](#project-layout)
12. [Git: clone, branch, push](#git-clone-branch-push)
13. [New Alembic migrations](#new-alembic-migrations)
14. [Security](#security)

---

## What you need

- **Python 3.11+**
- **Git**
- **PostgreSQL** — recommended when connecting the web or mobile app to a real API; use `DATABASE_URL` as in `.env.example`.
- **SQLite** — optional zero-install alternative if you leave `DATABASE_URL` as `sqlite:///./minoto.db`.

---

## Quick start (PostgreSQL, recommended)

Use this when you want the same setup as the Minoto web app (see repo root **README**).

1. **Install PostgreSQL** and create an **empty** database (for example `minoto_dev`). See also [PostgreSQL notes](#postgresql-notes).

2. **Clone** this repo, branch **`mom-be`** (see [Git](#git-clone-branch-push)).

3. **Virtual environment** (from the `backend` folder):

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

4. **Environment file**

   ```powershell
   copy .env.example .env
   ```

   Edit **`.env`**: set `DATABASE_URL` to your Postgres URL, for example:

   `postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/minoto_dev`

   Keep **`CORS_ORIGINS`** including `http://localhost:5173` if you use the Vite dev server.

5. **Migrations**

   ```powershell
   python -m alembic upgrade head
   ```

6. **Run the server** — [Run the server](#run-the-server).

---

## Quick start (SQLite)

All commands assume a terminal **in this `backend` folder** (the one that contains `main.py`).

1. **Clone** the repo and use branch **`mom-be`** (see [Git](#git-clone-branch-push) for the URL).

2. **Create and activate a venv** (see [Virtual environment](#virtual-environment-windows) for PowerShell vs **cmd**).

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Environment file**

   ```powershell
   copy .env.example .env
   ```

   For local SQLite you usually **do not** need to edit `.env` unless you change ports, CORS, or secrets.

4. **Apply database migrations** (creates/updates tables — required even for SQLite):

   ```powershell
   python -m alembic upgrade head
   ```

5. **Start the API** (see [Run the server](#run-the-server)).

---

## Virtual environment (Windows)

**PowerShell**

```powershell
.\.venv\Scripts\Activate.ps1
```

If scripts are disabled: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, then run `Activate.ps1` again.  
Or use a **one-session** bypass: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` before activating.

**Command Prompt (`cmd`)**

```bat
.\.venv\Scripts\activate.bat
```

**Without activating** (still from `backend/`):

```bat
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## Environment variables (`.env`)

| Variable | Purpose |
| -------- | ------- |
| `DATABASE_URL` | DB connection. **Recommended:** `postgresql+psycopg2://USER:PASSWORD@localhost:5432/DBNAME` (see `.env.example`). **SQLite:** `sqlite:///./minoto.db` (file next to `main.py`) if you skip Postgres. |
| `CORS_ORIGINS` | Comma-separated web origins (e.g. `http://localhost:3000,http://localhost:5173`). Native mobile apps are not limited by CORS the same way browsers are. |
| `UPLOAD_ROOT` | Folder for uploaded files (under `backend/`). Created at startup with parents. |
| `MAX_VOICE_UPLOAD_MB` | Max voice upload size (MB). |
| `SECRET_KEY` | JWT signing key. Has an insecure **dev default** in code if unset — **set a strong value in production**. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Optional; defaults to 7 days in code. |
| `APP_NAME`, `DEBUG`, `API_V1_PREFIX` | Optional overrides. |

Copy from **`.env.example`**; never commit **`.env`**.

---

## Database & migrations

- **SQLite (default):** zero server install; database file is typically **`minoto.db`** next to `main.py` when using `sqlite:///./minoto.db`.
- **PostgreSQL:** set `DATABASE_URL` and create an **empty** database first (see [PostgreSQL notes](#postgresql-notes)).

**Apply or update schema** (after clone or `git pull` when migrations changed):

```powershell
python -m alembic upgrade head
```

Use `python -m alembic` so you do not rely on `alembic` being on the system `PATH` (common on Windows).

**Revisions in repo (examples):**

- **`001_initial_schema`** — users, members, meetings, `meeting_members`, `meeting_live_sessions`
- **`002_add_user_avatar_url`** — adds `users.avatar_url`

If Alembic cannot connect, fix `DATABASE_URL` and ensure the DB exists (for Postgres).

---

## Run the server

Stay in **`backend/`**. With the venv active:

```powershell
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Equivalent if `uvicorn` is on your PATH:

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Static uploads are served under **`/media/...`** (see `main.py`); upload directory is ensured at import time.

---

## Verify it works

- **Swagger UI:** http://127.0.0.1:8000/docs  
- **Health:** http://127.0.0.1:8000/api/v1/health  

---

## API reference

**`API_DOCUMENTATION.txt`** in this folder lists routes, bodies, and responses for the team. **`GET /openapi.json`** is also available from a running server.

---

## PostgreSQL notes

Skip this section if you use **SQLite** only.

You are not installing a second PostgreSQL **server** — only ensuring a **database** exists for the URL in `.env`.

**Typical pgAdmin flow**

1. Open **pgAdmin** → connect to your server (e.g. PostgreSQL 18).
2. **Databases** → right-click → **Create** → **Database…**
3. Name must match the database in `DATABASE_URL` (example: `minoto_dev`). Owner often `postgres` → **Save**.

Tables are created by **Alembic**, not by hand.

If no server appears in pgAdmin: **Register** → **Server** with host `localhost`, port `5432`, user `postgres`, and your password.

---

## Project layout

| Path | Role |
| ---- | ---- |
| `main.py` | FastAPI app entry, CORS, `/media` mount, includes `api_router` |
| `api/v1/` | Versioned routers: `auth`, `users`, `members`, `meetings`, `sessions`, `stats` |
| `routes/` | Small shared routes (e.g. `health`) wired from `api/v1/router.py` |
| `models/` | SQLAlchemy ORM |
| `schemas/` | Pydantic request/response models |
| `services/` | Security, pagination, file storage, meeting presentation helpers |
| `utils/` | IDs, date/duration formatting |
| `config/` | Settings loaded from `.env` |
| `db/` | Engine and `SessionLocal` |
| `alembic/` | Migrations under `alembic/versions/` |

There is no top-level `app/` package.

---

## Git: clone, branch, push

**Remote:** [github.com/sheharyar-mansha/minoto_backend](https://github.com/sheharyar-mansha/minoto_backend) — default branch **`mom-be`**.

**Clone**

```powershell
git clone -b mom-be https://github.com/sheharyar-mansha/minoto_backend.git
cd minoto_backend
```

**Workflow for changes**

```powershell
git checkout mom-be
git pull origin mom-be
git checkout -b feature/your-short-description
# edit, commit
git push -u origin feature/your-short-description
```

Open a **pull request** into **`mom-be`** on GitHub.

**First-time `origin` on your machine** (if missing):

```powershell
git remote add origin https://github.com/sheharyar-mansha/minoto_backend.git
git branch -M mom-be
git push -u origin mom-be
```

**GitHub settings (team)**

- Set **default branch** to **`mom-be`** if needed: **Settings → General → Default branch**.
- Optional: **branch protection** on **`mom-be`** (require PR before merge, etc.).

Teammates only need this repo, venv, `.env`, migrations, and **uvicorn** — no mobile repo required to run the API.

---

## New Alembic migrations

When you **change** SQLAlchemy models and need a shared schema update:

```powershell
python -m alembic revision --autogenerate -m "short description"
python -m alembic upgrade head
```

Commit new files under **`alembic/versions/`** and push on your **feature branch** for review.

Ensure new model modules are imported in **`alembic/env.py`** (see comment there) before autogenerate.

---

## Security

- **`.gitignore`** excludes **`.env`**, **`uploads/`**, local DB files as configured, and venv folders.
- Commit only **`.env.example`** (no real passwords or production `SECRET_KEY`).
- Use a strong **`SECRET_KEY`** and locked-down **`DATABASE_URL`** in production.

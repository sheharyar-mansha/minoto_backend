# MOM backend (Python API)

This is the **only** part of the product that belongs on GitHub. All frontends stay on each developer’s machine.

Default Git branch: **`mom-be`** (not `main`).

## What you need on your PC

- Python 3.11+ installed
- PostgreSQL running somewhere you can connect to (later — set `DATABASE_URL` in `.env`)

## First-time setup

Open a terminal **inside this `backend` folder**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`: set `DATABASE_URL` to your Postgres connection string, for example:

`postgresql+psycopg2://USER:PASSWORD@localhost:5432/YOUR_DB_NAME`

## Run the server

With the venv active:

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- Docs: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/api/v1/health  

## Database migrations (after Postgres works)

```powershell
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

If Alembic errors, your `DATABASE_URL` is wrong or Postgres is not reachable.

When you add real tables: put model classes under `models/`, import those modules in `alembic/env.py` (see the comment there), then run `revision --autogenerate` again.

## Folders

| Folder     | What it’s for        |
| ---------- | -------------------- |
| `routes/`  | API paths (e.g. health) |
| `models/`  | Database tables (SQLAlchemy) |
| `schemas/` | Request/response shapes (Pydantic) |
| `config/`  | Settings from `.env` |
| `db/`      | DB connection helpers |
| `alembic/` | Migration scripts |

There is no `app/` package — the entry file is **`main.py`**.

---

## GitHub (backend only)

### 1. Create the repository

On GitHub: **New repository** → name it (e.g. `mom-be` or `minoto-api`) → **empty** repo (no README, no .gitignore from GitHub if you already have them here).

### 2. Push this folder using branch `mom-be`

From **`backend/`** (first time):

```powershell
git add .
git commit -m "Initial API"
git branch -M mom-be
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin mom-be
```

### 3. Make `mom-be` the default branch

On GitHub: **Settings → General → Default branch** → set to **`mom-be`** → Update.

You can ignore `main` or delete it on GitHub if it was never used. The team should use **`mom-be`** as the protected line you merge into.

### 4. Protect `mom-be` (recommended)

**Settings → Branches → Add branch protection rule**

- Branch name pattern: `mom-be`
- Turn on: **Require a pull request before merging** (optional but good for teams)
- Turn on: **Do not allow bypassing** (optional)
- Often enabled: **Require status checks** once you add CI

Repeat for **`main` only if you still use `main`** on that repo; if you only use `mom-be`, one rule is enough.

### 5. What teammates do

They clone the repo, checkout **`mom-be`**, create a venv, copy `.env.example` → `.env`, and run `uvicorn` like above. They do **not** need your frontend.

### 6. Never commit secrets

`.gitignore` already ignores `.env`. Only commit `.env.example` (no real passwords).

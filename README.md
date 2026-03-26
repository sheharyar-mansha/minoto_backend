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

### PostgreSQL + pgAdmin (create the empty database)

You are **not** installing a second copy of PostgreSQL. The real database **server** is already running (the one you installed, e.g. **PostgreSQL 18**). pgAdmin is only a **GUI client** that talks to it.

**Usual path (you already see “PostgreSQL 18” under Servers):**

1. Open **pgAdmin** and click **PostgreSQL 18** (enter the `postgres` password if asked).
2. Expand **Databases** → right-click **Databases** → **Create** → **Database…**.
3. **Database** name: `minoto_dev` (must match the name at the end of `DATABASE_URL` in `.env`). **Owner**: `postgres` → **Save**.
4. Done — no need to create tables by hand; Alembic does that after you add models and run migrations.

**Only if you do *not* see any server in the left panel:** then use **Servers** → right-click **Servers** → **Register** → **Server** and enter Host `localhost`, Port `5432`, User `postgres`, and your password. That step only saves a **connection** in pgAdmin; it does not replace or duplicate PostgreSQL itself.

If your `.env` uses another database name, use that name in step 3 instead of `minoto_dev`.

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

**Remote:** [github.com/sheharyar-mansha/minoto_backend](https://github.com/sheharyar-mansha/minoto_backend)  
Default branch: **`mom-be`**.

### 1. Clone (teammates / new machine)

```powershell
git clone -b mom-be https://github.com/sheharyar-mansha/minoto_backend.git
cd minoto_backend
```

### 2. Push from this folder (first time on your PC)

From **`backend/`** (if you have not added `origin` yet):

```powershell
git remote add origin https://github.com/sheharyar-mansha/minoto_backend.git
git branch -M mom-be
git push -u origin mom-be
```

If `origin` already exists, skip `remote add` and only run `git push -u origin mom-be`.

### 3. Make `mom-be` the default branch on GitHub

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

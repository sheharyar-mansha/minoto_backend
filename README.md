# MOM backend (Python API)

This is the **only** part of the product that belongs on GitHub. All frontends stay on each developer’s machine.

Default Git branch: **`mom-be`** (not `main`).

## What you need on your PC

- Python 3.11+ installed
- PostgreSQL **or** use the default **SQLite** file (`minoto.db` in this folder) for quick local work

## First-time setup

Open a terminal **inside this `backend` folder**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

- **`DATABASE_URL`** — leave default SQLite for zero setup, or set Postgres, e.g.  
  `postgresql+psycopg2://USER:PASSWORD@localhost:5432/YOUR_DB_NAME`

**Full HTTP reference for the team:** see **`API_DOCUMENTATION.txt`** in this folder (every path, body, and response).

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

Stay in **`backend/`** (the folder that contains `main.py`). With the venv active:

```powershell
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

If `uvicorn` is on your PATH (venv `Scripts` folder), this is equivalent:

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- Docs: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/api/v1/health  

## Database migrations

### Teammate: clone repo, configure Postgres, then apply migrations

1. **Clone** the default branch (should be **`mom-be`**):

   ```powershell
   git clone -b mom-be https://github.com/sheharyar-mansha/minoto_backend.git
   cd minoto_backend
   ```

2. **Python env** (from the repo root — the folder that contains `main.py`):

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Environment file:** `copy .env.example .env` and set **`DATABASE_URL`**. Create an **empty** database in pgAdmin (name must match the database in that URL).

4. **Apply migrations** (this is what most people do — it runs the SQL already committed under `alembic/versions/`):

   ```powershell
   alembic upgrade head
   ```

5. **Pull new code later:** when someone adds migrations, run **`git pull`** then **`alembic upgrade head`** again.

If Alembic cannot connect, fix `DATABASE_URL` or Postgres (service running, database exists, user/password correct).

Initial schema is in **`alembic/versions/001_initial_schema.py`**. After `upgrade head`, tables exist for users, members, meetings, rosters, and live session sync.

### Who creates new migrations?

Only when **you change** SQLAlchemy models and want to update the database schema for everyone:

```powershell
alembic revision --autogenerate -m "short description"
alembic upgrade head
```

Commit the **new files** under `alembic/versions/` and push so teammates get them on the next `git pull`.

When you add models: put classes under `models/`, import those modules in `alembic/env.py` (see the comment there), then use `revision --autogenerate`.

## Folders

| Folder       | What it’s for |
| ------------ | ---------------- |
| `api/`       | Versioned routers (`api/v1/`), shared `deps` (auth, pagination) |
| `routes/`    | Legacy tiny routers included from v1 (e.g. health) |
| `models/`    | SQLAlchemy ORM |
| `schemas/`   | Pydantic request/response models |
| `services/`  | Security, pagination, file storage, meeting presentation helpers |
| `utils/`     | IDs, date/duration formatting |
| `config/`    | Settings from `.env` |
| `db/`        | Engine, sessions |
| `alembic/`   | Migrations (`alembic/versions/`) |

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

They clone the repo, checkout **`mom-be`**, create a venv, copy `.env.example` → `.env`, and start the API with **`python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000`** from **`backend/`** (see **Run the server** above). They do **not** need your frontend.

### 6. Never commit secrets

`.gitignore` already ignores `.env`. Only commit `.env.example` (no real passwords).

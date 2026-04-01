# Neighborhood Commerce & Content Operations Management System

Backend service for a local group-leader commerce model with catalog/search, inventory, settlements, content/templates, messaging, and admin governance.

## Tech Stack

- Python, Flask, SQLAlchemy, Alembic
- SQLite (single-machine/offline deployment)
- Flask-SocketIO (messaging transport)
- APScheduler (background jobs)

## Core Capabilities

- Auth + RBAC with session token (`Bearer`) flow
- Communities, service areas, and group-leader bindings
- Commission rules, settlement runs, and disputes
- Catalog management + search/autocomplete/history/trending
- Multi-warehouse inventory with FIFO or moving-average costing
- Content/versioning/templates with publish/rollback + migrations
- Admin tickets, audit log, health/readiness, structured logs

## Project Layout

```text
repo/
├── app/                 # Flask application
├── migrations/          # Alembic migrations
├── scripts/             # start.sh, seed, migrate (ci_run_tests.sh optional alias)
├── unit_tests/          # Unit tests
├── API_tests/           # API functional tests
├── run_tests.sh / run_tests.ps1
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

Documentation: `docs/` (prompt, questions, API spec, design).

## Prerequisites

- Docker
- Docker Compose

## Run the system (Docker only)

From the `repo/` directory:

```bash
docker compose up --build
```

On first start and on every restart, the container entrypoint:

1. Creates a Fernet encryption key under the mounted `data/keys/` volume if it is missing  
2. Applies database schema with **Alembic migrations** (`flask db upgrade`)  
3. Runs the **seed script** (idempotent; re-runs are safe)  
4. Starts the API on port **5000**

You do **not** run migrations, seeding, or `.env` setup manually—Compose and the image handle it.

Open the app:

- API: `http://localhost:5000`
- Health: `http://localhost:5000/health`
- Readiness: `http://localhost:5000/health/ready`
- Versioned API: `http://localhost:5000/api/v1`

Stop:

```bash
docker compose down
```

Runtime data (SQLite DB, keys, logs, attachments) lives under `repo/data/` as a **single** Compose bind mount (`./data:/app/data`). Do not bind-mount only `db.sqlite3` by file path on an empty host tree, or Docker may create a **directory** named `db.sqlite3` and SQLite will fail with `unable to open database file`.

## Optional: override Compose defaults

You can pass environment variables on the command line when starting the stack, for example:

```bash
FLASK_ENV=production APP_VERSION=0.2.0 SECRET_KEY=your-secret docker compose up --build
```

If you omit them, defaults are defined in `docker-compose.yml`.

## Tests

**Required command (acceptance):** from `repo/` run:

```bash
bash run_tests.sh
```

- **Host with dependencies:** run `pip install -r requirements.txt` first; tests execute on your machine.
- **Host without pytest (e.g. CI):** the same `run_tests.sh` detects that, and **re-runs itself inside** the Docker app image (needs `docker compose` and an image build — run `docker compose build` once in the job before `bash run_tests.sh`).

On Windows: `powershell -ExecutionPolicy Bypass -File run_tests.ps1` (host with deps only).

Optional: `bash scripts/ci_run_tests.sh` is only a thin wrapper that calls `run_tests.sh`.

### Already-running container

```bash
docker compose exec app bash run_tests.sh
```

## Notes

- Intended for single-machine / offline-style deployment.
- Replace the default `SECRET_KEY` Compose default before any real deployment.
- Do not commit `repo/data/keys/` or production databases; those paths are gitignored in `repo/.gitignore`.

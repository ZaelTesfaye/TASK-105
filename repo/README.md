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
├── backend/
│   ├── app/               # Flask application (routes, models, services, middleware)
│   ├── config/            # Clean Config module (single source of truth for env vars)
│   ├── logging/           # Centralized Logger definition
│   └── tests/
│       ├── unit/          # Isolated unit tests
│       ├── api/           # API functional tests
│       └── integration/   # Integration / job tests
├── migrations/            # Alembic schema migrations
├── scripts/               # start.sh, seed, migrate helpers
├── docker-compose.yml     # Main orchestration (defines all env vars)
├── run_tests.sh           # Global test execution script
├── Dockerfile
├── requirements.txt
└── README.md
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

You do **not** run migrations, seeding, or `.env` setup manually -- Compose and the image handle it.

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

## Environment Variables

All environment variables are defined in `docker-compose.yml` and centralized through `backend/config/` (the Clean Config module). Application logic never reads `os.environ` directly.

| Variable | Default | Description |
|---|---|---|
| `FLASK_ENV` | `production` | Config profile (development/testing/production) |
| `SECRET_KEY` | `change-me-for-production` | Flask secret key |
| `DATABASE_URL` | `sqlite:////app/data/db.sqlite3` | SQLAlchemy connection string |
| `FERNET_KEY_PATH` | `/app/data/keys/secret.key` | Fernet encryption key path |
| `LOG_FILE` | `/app/data/logs/app.jsonl` | Structured JSON log output |
| `ATTACHMENT_DIR` | `/app/data/attachments` | File upload directory |
| `JOBS_ENABLED` | `true` | Enable background jobs |
| `ENABLE_TLS` | `false` | TLS toggle (Boolean) |

Override on the command line:

```bash
FLASK_ENV=production SECRET_KEY=your-secret docker compose up --build
```

## Tests

**Pre-merge acceptance gate:** every change must pass the full suite below with **exit code 0** before merging to the main branch. Use `run_tests.sh` (Unix/macOS/CI) or `run_tests.ps1` (Windows with Python deps). No merge without a green run.

**Required command (acceptance):** from `repo/` run:

```bash
bash run_tests.sh
```

- **Host with dependencies:** run `pip install -r requirements.txt` first; tests execute on your machine.
- **Host without pytest (e.g. CI):** the same `run_tests.sh` detects that, and **re-runs itself inside** the Docker app image (needs `docker compose` and an image build -- run `docker compose build` once in the job before `bash run_tests.sh`).

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

Project Type: backend

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
docker-compose up --build
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
docker-compose down
```

Runtime data (SQLite DB, keys, logs, attachments) lives under `repo/data/` as a **single** Compose bind mount (`./data:/app/data`). Do not bind-mount only `db.sqlite3` by file path on an empty host tree, or Docker may create a **directory** named `db.sqlite3` and SQLite will fail with `unable to open database file`.

## Verify the System is Working

After starting the system, run the following commands to confirm everything is operational:

```bash
# 1. Confirm health
curl http://localhost:5000/health

# 2. Login with the admin account
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "AdminPass1234!"}'

# 3. Use the returned token on a protected endpoint
curl http://localhost:5000/api/v1/users \
  -H "Authorization: Bearer <token_from_step_2>"
```

Replace `<token_from_step_2>` with the `token` value from the login response.

## Demo Credentials

The seed script creates the following accounts on first start. All roles in the RBAC system are represented:

| Role               | Username            | Password         |
|--------------------|---------------------|------------------|
| Administrator      | admin               | AdminPass1234!   |
| Operations Manager | opsmanager          | OpsPass1234!     |
| Moderator          | moderator           | ModPass1234!     |
| Group Leader       | gl_alice            | AlicePass1234!   |
| Staff              | staff@example.com   | Staff1234!       |
| Member             | member_bob          | BobPass1234!     |

All six RBAC roles are seeded on first start.

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
FLASK_ENV=production SECRET_KEY=your-secret docker-compose up --build
```

## Tests

All testing is Docker-contained. Host-level Python dependency setup is neither required nor supported.

**Pre-merge acceptance gate:** every change must pass the full suite below with **exit code 0** before merging to the main branch.

**Required command (acceptance):** from `repo/` run:

```bash
bash run_tests.sh
```

Run tests with:

```bash
docker-compose run --rm backend pytest
```

### Already-running container

```bash
docker-compose exec backend pytest
```

## Notes

- Intended for single-machine / offline-style deployment.
- Replace the default `SECRET_KEY` Compose default before any real deployment.
- Do not commit `repo/data/keys/` or production databases; those paths are gitignored in `repo/.gitignore`.

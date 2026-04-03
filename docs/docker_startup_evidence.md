# Docker startup evidence (TASK-105)

**Purpose:** Close the container-runtime verification boundary for the Neighborhood Commerce API (`repo/`).

**When:** 2026-04-03 (local run, Docker Desktop).

**Environment**

- Host: Windows 10, Docker Compose v2.40.3-desktop.1
- Working directory: `C:\TASK-105\repo`
- Compose file: `repo/docker-compose.yml` (single `app` service, SQLite under `./data`)

**Commands executed**

1. `docker compose build` — image `repo-app:latest` built successfully (Python 3.12-slim base, `requirements.txt`, app copy).
2. `docker compose up -d` — container `repo-app-1` started; entrypoint `bash scripts/start.sh` (migrations, seed, `flask run` on port 5000).

*(Equivalent to `docker compose up --build -d` in one step for routine use.)*

**Runtime checks (host → container)**

| Check | Result |
|--------|--------|
| `GET http://127.0.0.1:5000/health` | HTTP 200 — `{"db":"ok","status":"ok","version":"0.1.0"}` |
| `GET http://127.0.0.1:5000/health/ready` | HTTP 200 — `{"status":"ready"}` |

**Container state (excerpt)**

- Service `app`: image `repo-app`, ports `0.0.0.0:5000->5000/tcp`, state **running**, exit code 0.

**Notes**

- Docker Desktop reported orphan containers from another compose project sharing the default project name; they are unrelated to this `docker-compose.yml` (which defines only `app`). The API under test is `repo-app-1` on port 5000.
- For a clean re-check: from `repo/`, run `docker compose up --build -d`, wait for migrations/seed to finish (~10–30 s), then call `/health` and `/health/ready` as above.

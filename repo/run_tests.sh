#!/usr/bin/env bash
# ============================================================
# run_tests.sh — One-click test runner for the acceptance suite (required entry point).
# Mandatory pre-merge gate: exit 0 required before merging (see README.md § Tests).
# Run from repo/:  bash run_tests.sh
#
# All tests run inside Docker. No host-level Python or pip installation is
# required or supported.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$ROOT"

# ── Docker required ─────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "Error: Docker is required. Please install Docker and try again." && exit 1
fi

# ── Build image if needed ───────────────────────────────────
cd "$REPO"
docker compose build --quiet

# ── Colour helpers ──────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[PASS]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }

echo ""
echo "========================================================"
echo "  Acceptance Test Suite — Neighborhood Commerce System"
echo "========================================================"
echo ""

# ── Common docker compose run prefix ───────────────────────
RUN="docker compose run -T --rm --no-deps -e FLASK_ENV=testing -e FERNET_KEY_PATH=/app/data/keys/secret.key -e LOG_FILE=/app/data/logs/app.jsonl -e ATTACHMENT_DIR=/app/data/attachments --entrypoint ''"

# ── Ensure data dirs and Fernet key inside the container ────
info "Ensuring data directories and Fernet key …"
docker compose run -T --rm --no-deps --entrypoint "" \
    app bash -c "
mkdir -p /app/data/keys /app/data/logs /app/data/attachments
if [ ! -f /app/data/keys/secret.key ]; then
    python -c \"
from cryptography.fernet import Fernet
with open('/app/data/keys/secret.key', 'wb') as f:
    f.write(Fernet.generate_key())
\"
fi
"

# ── Run unit tests ───────────────────────────────────────────
echo ""
echo "--------------------------------------------------------"
echo "  PHASE 1 — Unit Tests  (backend/tests/unit/)"
echo "--------------------------------------------------------"
UNIT_RESULT=0
docker compose run -T --rm --no-deps --entrypoint "" \
    -e FLASK_ENV=testing \
    -e FERNET_KEY_PATH=/app/data/keys/secret.key \
    -e LOG_FILE=/app/data/logs/app.jsonl \
    -e ATTACHMENT_DIR=/app/data/attachments \
    app python -m pytest backend/tests/unit/ \
    -v --tb=short --no-header -q \
    2>&1 || UNIT_RESULT=$?

# ── Run API functional tests ─────────────────────────────────
echo ""
echo "--------------------------------------------------------"
echo "  PHASE 2 — API Functional Tests  (backend/tests/api/)"
echo "--------------------------------------------------------"
API_RESULT=0
docker compose run -T --rm --no-deps --entrypoint "" \
    -e FLASK_ENV=testing \
    -e FERNET_KEY_PATH=/app/data/keys/secret.key \
    -e LOG_FILE=/app/data/logs/app.jsonl \
    -e ATTACHMENT_DIR=/app/data/attachments \
    app python -m pytest backend/tests/api/ \
    -v --tb=short --no-header -q \
    2>&1 || API_RESULT=$?

# ── Run integration / job tests ──────────────────────────────
echo ""
echo "--------------------------------------------------------"
echo "  PHASE 3 — Integration/Job Tests  (backend/tests/integration/)"
echo "--------------------------------------------------------"
JOBS_RESULT=0
docker compose run -T --rm --no-deps --entrypoint "" \
    -e FLASK_ENV=testing \
    -e FERNET_KEY_PATH=/app/data/keys/secret.key \
    -e LOG_FILE=/app/data/logs/app.jsonl \
    -e ATTACHMENT_DIR=/app/data/attachments \
    app python -m pytest backend/tests/integration/ \
    -v --tb=short --no-header -q \
    2>&1 || JOBS_RESULT=$?

# ── Coverage report ──────────────────────────────────────────
echo ""
echo "--------------------------------------------------------"
echo "  PHASE 4 — Coverage Report"
echo "--------------------------------------------------------"
COV_RESULT=0
docker compose run -T --rm --no-deps --entrypoint "" \
    -e FLASK_ENV=testing \
    -e FERNET_KEY_PATH=/app/data/keys/secret.key \
    -e LOG_FILE=/app/data/logs/app.jsonl \
    -e ATTACHMENT_DIR=/app/data/attachments \
    app python -m pytest backend/tests/unit/ backend/tests/api/ backend/tests/integration/ \
    --cov=app \
    --cov-report=term-missing:skip-covered \
    --cov-report=html:htmlcov \
    --tb=no -q \
    2>&1 || COV_RESULT=$?

# ── Aggregate summary ────────────────────────────────────────
echo ""
echo "========================================================"
echo "  SUMMARY"
echo "========================================================"
echo ""
info "Unit tests:         $([ $UNIT_RESULT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
info "API tests:          $([ $API_RESULT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
info "Integration tests:  $([ $JOBS_RESULT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
echo ""

if [ "$UNIT_RESULT" -eq 0 ] && [ "$API_RESULT" -eq 0 ] && [ "$JOBS_RESULT" -eq 0 ]; then
    ok "All tests passed."
    exit 0
else
    fail "One or more tests failed."
    [ "$UNIT_RESULT"  -ne 0 ] && fail "  Unit tests:         FAILED (exit $UNIT_RESULT)"
    [ "$API_RESULT"   -ne 0 ] && fail "  API tests:          FAILED (exit $API_RESULT)"
    [ "$JOBS_RESULT"  -ne 0 ] && fail "  Integration tests:  FAILED (exit $JOBS_RESULT)"
    exit 1
fi

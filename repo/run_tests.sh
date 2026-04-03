#!/usr/bin/env bash
# ============================================================
# run_tests.sh — One-click test runner for the acceptance suite (required entry point).
# Run from repo/:  bash run_tests.sh
#
# - If this Python has pytest (after pip install -r requirements.txt), tests run on the host.
# - If pytest is missing (typical CI with only Docker), this script re-invokes itself inside
#   the app image so the same file path still satisfies "run run_tests.sh".
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$ROOT"

# Re-run inside Docker once when host has no pytest (avoids requiring a second script name).
if [ "${RUN_TESTS_SH_IN_CONTAINER:-}" != "1" ]; then
  if ! python -m pytest --version >/dev/null 2>&1; then
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
      echo "[INFO]  pytest not found on host — running the same run_tests.sh inside Docker..."
      cd "$REPO"
      exec env RUN_TESTS_SH_IN_CONTAINER=1 \
        docker compose run -T --rm --no-deps \
        --entrypoint "" \
        -e RUN_TESTS_SH_IN_CONTAINER=1 \
        app bash /app/run_tests.sh "$@"
    fi
  fi
fi

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

# ── Prerequisites ────────────────────────────────────────────
info "Checking Python …"
python --version 2>&1 || { fail "python not found — install Python 3.12+"; exit 1; }

info "Checking pytest …"
python -m pytest --version 2>&1 || {
  fail "pytest not found — run: pip install -r requirements.txt, or install Docker and docker compose"
  exit 1
}

# ── Data directories and Fernet key ─────────────────────────
info "Ensuring data directories exist …"
mkdir -p "$REPO/data/keys" "$REPO/data/logs" "$REPO/data/attachments"

if [ ! -f "$REPO/data/keys/secret.key" ]; then
    info "Generating Fernet encryption key …"
    python -c "
from cryptography.fernet import Fernet
with open('$REPO/data/keys/secret.key', 'wb') as f:
    f.write(Fernet.generate_key())
"
    ok "Key written to $REPO/data/keys/secret.key"
fi

# ── Environment ──────────────────────────────────────────────
export PYTHONPATH="$REPO"
export FERNET_KEY_PATH="$REPO/data/keys/secret.key"
export LOG_FILE="$REPO/data/logs/app.jsonl"
export ATTACHMENT_DIR="$REPO/data/attachments"

cd "$ROOT"

# ── Run unit tests ───────────────────────────────────────────
echo ""
echo "--------------------------------------------------------"
echo "  PHASE 1 — Unit Tests  (unit_tests/)"
echo "--------------------------------------------------------"
UNIT_RESULT=0
python -m pytest unit_tests/ \
    -v \
    --tb=short \
    --no-header \
    -q \
    2>&1 || UNIT_RESULT=$?

# ── Run API functional tests ─────────────────────────────────
echo ""
echo "--------------------------------------------------------"
echo "  PHASE 2 — API Functional Tests  (API_tests/)"
echo "--------------------------------------------------------"
API_RESULT=0
python -m pytest API_tests/ \
    -v \
    --tb=short \
    --no-header \
    -q \
    2>&1 || API_RESULT=$?

# ── Run integration / job tests ──────────────────────────────────────────────
echo ""
echo "--------------------------------------------------------"
echo "  PHASE 3 — Integration/Job Tests  (tests/)"
echo "--------------------------------------------------------"
JOBS_RESULT=0
python -m pytest tests/ \
    -v \
    --tb=short \
    --no-header \
    -q \
    2>&1 || JOBS_RESULT=$?

# ── Aggregate summary ────────────────────────────────────────
echo ""
echo "========================================================"
echo "  SUMMARY"
echo "========================================================"
python -m pytest unit_tests/ API_tests/ tests/ \
    --tb=no \
    -q \
    2>&1 | tail -5

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

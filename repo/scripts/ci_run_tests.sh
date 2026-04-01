#!/usr/bin/env bash
# Optional alias for CI pipelines that already call this path.
# Acceptance criterion: use run_tests.sh — that script handles Docker automatically.
set -euo pipefail
cd "$(dirname "$0")/.."
exec bash run_tests.sh "$@"

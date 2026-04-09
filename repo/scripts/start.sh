#!/usr/bin/env bash
set -euo pipefail

# Ensure PYTHONPATH includes backend/ so `from app import ...` works
export PYTHONPATH="${PYTHONPATH:-/app/backend}"

# Ensure writable layout inside the mounted ./data volume (keys, logs, attachments, DB dir)
KEY_PATH="${FERNET_KEY_PATH:-data/keys/secret.key}"
LOG_PATH="${LOG_FILE:-data/logs/app.jsonl}"
ATTACH_DIR="${ATTACHMENT_DIR:-data/attachments}"
mkdir -p "$(dirname "$KEY_PATH")" "$(dirname "$LOG_PATH")" "$ATTACH_DIR"

# Generate Fernet key if none exists
if [ ! -f "$KEY_PATH" ]; then
  echo "Generating new Fernet key at $KEY_PATH"
  python - <<'EOF'
import os
from cryptography.fernet import Fernet
key_path = os.environ.get("FERNET_KEY_PATH", "data/keys/secret.key")
os.makedirs(os.path.dirname(key_path), exist_ok=True)
with open(key_path, "wb") as f:
    f.write(Fernet.generate_key())
EOF
fi

# Align Alembic with pre-existing SQLite files (e.g. old create_all DBs)
echo "Checking Alembic / SQLite state..."
python scripts/ensure_alembic_state.py

# Run migrations
echo "Running Alembic migrations..."
flask db upgrade

# Seed fixtures (idempotent; safe on every container start)
echo "Seeding database (idempotent)..."
python scripts/seed.py

# Start app via eventlet WSGI server
echo "Starting application..."
exec python -m flask run --host=0.0.0.0 --port=5000

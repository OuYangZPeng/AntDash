#!/usr/bin/env bash
# One-command launcher for the AntDash backend.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "Seeding demo data..."
python seed.py || true

PORT="${ANTDASH_PORT:-8080}"
echo "Starting AntDash API at http://127.0.0.1:${PORT} (docs at /docs)"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --reload

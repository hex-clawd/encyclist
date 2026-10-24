#!/usr/bin/env bash
# Launcher for the Encyclist web UI.
# Activates the project venv and runs `python -m web.app`.

set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Error: .venv not found. Create it first: python -m venv .venv && .venv/bin/pip install -e ." >&2
    exit 1
fi

# shellcheck source=/dev/null
source .venv/bin/activate

if [ ! -f ".env" ]; then
    echo "Warning: .env not found. Copy .env.example to .env and add your API key." >&2
fi

exec python -m web.app

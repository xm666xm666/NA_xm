#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYCMD=""
if command -v python3 &>/dev/null; then PYCMD=python3
elif command -v python &>/dev/null; then PYCMD=python
else echo "[ERROR] Python not found"; exit 1; fi

if [[ ! -f .venv/bin/python ]]; then
  echo "Creating virtual environment..."
  "$PYCMD" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -r requirements.txt -q
exec python app.py "$@"

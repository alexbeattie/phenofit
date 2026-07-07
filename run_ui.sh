#!/usr/bin/env bash
#
# run_ui.sh — launch the PhenoFit web UI.
#
# Prefers the project venv, falls back to python3. The server auto-falls back to
# the next free port if the requested one is busy.
#
#   ./run_ui.sh              # http://localhost:8000 (or next free port)
#   ./run_ui.sh --port 8080
#   ./run_ui.sh --no-open    # don't auto-open a browser

set -u

if [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

exec "$PY" -m phenofit.webapp "$@"

#!/usr/bin/env bash
# Setup the Python virtual environment for codec-comparison-pilot.
# Idempotent: safe to re-run. Detects existing .venv and skips creation.
#
# Usage:
#   ./scripts/setup_env.sh
#
# After running:
#   source .venv/bin/activate
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

# Pick a Python interpreter. Prefer python3, fall back to python.
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  echo "ERROR: no python interpreter found in PATH." >&2
  exit 1
fi

# Require Python 3.10+
PY_VERSION=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PY_MAJOR=${PY_VERSION%%.*}
PY_MINOR=${PY_VERSION##*.}
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "ERROR: Python 3.10+ required, found $PY_VERSION." >&2
  exit 1
fi
echo "Using Python: $PYTHON_BIN ($PY_VERSION)"

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating venv at $VENV_DIR ..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Upgrade pip and install deps
python -m pip install --upgrade pip wheel setuptools
python -m pip install -r "$PROJECT_ROOT/requirements.txt"

echo ""
echo "Done. Activate the venv with:"
echo "  source $VENV_DIR/bin/activate"

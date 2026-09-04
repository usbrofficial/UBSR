#!/usr/bin/env bash
# Run Mirage straight from this checkout (for development or trying it out without installing).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -x "$HERE/.venv/bin/python" ]; then
  python3 -m venv --system-site-packages "$HERE/.venv"
  "$HERE/.venv/bin/pip" install --quiet -r "$HERE/requirements.txt"
fi
cd "$HERE"
exec "$HERE/.venv/bin/python" -m mirage "$@"

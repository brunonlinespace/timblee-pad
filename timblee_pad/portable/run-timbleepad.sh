#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${TIMBLEEPAD_PORTABLE_PYTHON:-python3}"
exec "$PYTHON" "$ROOT/main.py" "$@"

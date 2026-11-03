#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
python3 "$SCRIPT_DIR/release_check.py"
(
    cd "$PROJECT_ROOT"
    python3 -m unittest discover -s timblee_pad/qa/tests -v
)

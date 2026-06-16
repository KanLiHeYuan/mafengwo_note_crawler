#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

export DISPLAY="${DISPLAY:-:0}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -u mafengwo_runner.py --manual-login-only --no-headless


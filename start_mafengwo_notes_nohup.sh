#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-all}"
shift || true

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p data/logs
TS="$(date +"%Y%m%d_%H%M%S")"
LOG_FILE="data/logs/mafengwo_${MODE}_${TS}.log"
PID_FILE="data/logs/mafengwo_${MODE}_${TS}.pid"

PYTHON_BIN="${PYTHON_BIN:-python3}"

nohup "$PYTHON_BIN" -u mafengwo_runner.py --mode "$MODE" "$@" >> "$LOG_FILE" 2>&1 &
PID="$!"
echo "$PID" > "$PID_FILE"

echo "Started mafengwo crawler."
echo "Mode: $MODE"
echo "PID: $PID"
echo "Log: $ROOT_DIR/$LOG_FILE"
echo "Tail: tail -f $ROOT_DIR/$LOG_FILE"


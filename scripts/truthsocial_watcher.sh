#!/usr/bin/env zsh
set -euo pipefail

PROJECT_DIR="/Users/freedom33/Documents/New_project"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/truthsocial_watcher.log"
PID_FILE="$PROJECT_DIR/.truthsocial_watcher.pid"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

if [[ ! -f .env ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] ERROR: .env not found" >> "$LOG_FILE"
  exit 1
fi

echo $$ > "$PID_FILE"

last_tick="$(date +%s)"
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] watcher started pid=$$" >> "$LOG_FILE"

while true; do
  now="$(date +%s)"
  gap=$((now - last_tick))

  # 休眠恢复后 gap 会明显变大，立即执行一次监听
  if (( gap >= 50 )); then
    if (( gap > 90 )); then
      echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] wake/resume detected gap=${gap}s -> immediate run" >> "$LOG_FILE"
    fi

    /usr/bin/python3 "$PROJECT_DIR/truthsocial_monitor.py" --once >> "$LOG_FILE" 2>&1 || true
    last_tick="$now"
  fi

  sleep 1
done

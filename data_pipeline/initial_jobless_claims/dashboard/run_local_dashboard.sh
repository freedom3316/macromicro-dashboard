#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVE_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
PORT="${1:-8787}"

cd "$SERVE_ROOT"
python3 -m http.server "$PORT"

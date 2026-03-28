#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

python3 "$ROOT_DIR/scripts/fetch_fred_initial_claims.py" \
  --out-dir "$ROOT_DIR/data/raw/fred"

python3 "$ROOT_DIR/scripts/build_initial_claims_dataset.py" \
  --fred-latest "$ROOT_DIR/data/raw/fred/fred_icsa_latest.csv" \
  --macromicro-dir "$ROOT_DIR/data/raw/macromicro" \
  --out-csv "$ROOT_DIR/data/processed/initial_jobless_claims.csv" \
  --out-db "$ROOT_DIR/data/processed/initial_jobless_claims.sqlite"

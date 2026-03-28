#!/usr/bin/env zsh
set -euo pipefail

cd /Users/freedom33/Documents/New\ project

if [ ! -f .env ]; then
  echo "Missing .env. Please run: cp .env.example .env and fill required values."
  exit 1
fi

python3 truthsocial_monitor.py

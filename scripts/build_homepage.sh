#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Snapshot country labels from Redis/Postgres into homepage/data/countries.json
# before the static Next export. New marketing pages appear after this rebuild.
python3 "$ROOT/scripts/export_homepage_countries.py"

cd "$ROOT/homepage"
if [[ ! -d node_modules ]]; then
  npm install --silent
fi
npm run build:flask --silent

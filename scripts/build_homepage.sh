#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT/homepage"
if [[ ! -d node_modules ]]; then
  npm install --silent
fi
npm run build:flask --silent

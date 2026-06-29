#!/usr/bin/env bash
# Same pytest + coverage gate as GitHub Actions CI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/pytest" ]]; then
  PYTEST="$ROOT/.venv/bin/pytest"
elif command -v pytest >/dev/null 2>&1; then
  PYTEST=pytest
else
  echo "pytest not found. Install deps: pip install -r requirements-dev.txt" >&2
  exit 1
fi

exec "$PYTEST" --cov --cov-report=term-missing \
  -o addopts="-ra --strict-markers -m 'not scrape'"

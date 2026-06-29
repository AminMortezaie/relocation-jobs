#!/usr/bin/env bash
# Point this repo at .githooks/ (pre-push runs tests before every push).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

chmod +x "$ROOT/.githooks/pre-push" "$ROOT/scripts/run_ci_tests.sh"

git config core.hooksPath .githooks

echo "Git hooks installed (core.hooksPath=.githooks)."
echo "pre-push will run: scripts/run_ci_tests.sh"
echo "Skip once: git push --no-verify"

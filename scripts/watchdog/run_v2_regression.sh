#!/usr/bin/env bash
# Transmission v2 Regression Suite
# Usage: ./run_v2_regression.sh
# Must be run from the watchdog/ directory.
# Exit 0 = all 14 tests pass. Exit 1 = regression detected.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "Transmission v2 Regression Suite"
echo "Baseline commit: 016faa8"
echo "Run at: $(date)"
echo "=================================================="
echo ""

python3 test_transmission.py

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo ""
  echo "✅ v2 baseline intact — safe to proceed with v3 work"
else
  echo ""
  echo "❌ REGRESSION DETECTED — do not merge v3 changes until resolved"
fi

exit $EXIT_CODE

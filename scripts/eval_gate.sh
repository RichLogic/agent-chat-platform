#!/usr/bin/env bash
# Eval gate — runs eval cases and exits non-zero if pass rate < 80%.
# Usage: ./scripts/eval_gate.sh [--cases DIR] [--output DIR]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

CASES_DIR="${1:-$BACKEND_DIR/eval/cases}"
OUTPUT_DIR="${2:-$BACKEND_DIR/eval/reports}"

echo "=== Eval Gate ==="
echo "Cases:  $CASES_DIR"
echo "Output: $OUTPUT_DIR"
echo ""

cd "$BACKEND_DIR"
PYTHONPATH=src:$PYTHONPATH python -m eval.runner --cases "$CASES_DIR" --output "$OUTPUT_DIR"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "PASS: eval gate passed (>= 80% pass rate)"
else
    echo ""
    echo "FAIL: eval gate failed (< 80% pass rate)"
fi

exit $EXIT_CODE

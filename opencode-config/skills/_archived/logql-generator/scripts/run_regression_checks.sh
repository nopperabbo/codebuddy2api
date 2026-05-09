#!/usr/bin/env bash
#
# Run logql-generator regression checks.
# - Static contract checks always run.
# - Runtime Loki checks are controlled by RUN_LOKI_RUNTIME_TESTS:
#   auto (default): run only when Docker is available
#   1/true: require runtime checks (fail if Docker is unavailable)
#   0/false: skip runtime checks
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly TEST_DIR="$SKILL_DIR/tests"

if [[ ! -d "$TEST_DIR" ]]; then
    echo "FAIL: tests directory not found: $TEST_DIR" >&2
    exit 1
fi

RUN_MODE="${RUN_LOKI_RUNTIME_TESTS:-auto}"

echo "Running logql-generator regression checks..."
echo "RUN_LOKI_RUNTIME_TESTS=${RUN_MODE}"
echo ""

PYTHONDONTWRITEBYTECODE=1 \
RUN_LOKI_RUNTIME_TESTS="$RUN_MODE" \
python3 -m unittest discover -s "$TEST_DIR" -p "test_*.py" -v

echo ""
echo "All logql-generator regression checks finished."

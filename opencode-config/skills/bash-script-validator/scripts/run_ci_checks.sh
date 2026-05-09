#!/usr/bin/env bash
#
# Deterministic CI runner for bash-script-validator.
# Uses system shellcheck only and fails fast when unavailable.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
TEST_SCRIPT="$SCRIPT_DIR/test_validate.sh"

if ! command -v shellcheck >/dev/null 2>&1; then
    echo "[ERROR] System shellcheck is required for deterministic CI checks." >&2
    echo "        Install shellcheck and re-run scripts/run_ci_checks.sh." >&2
    exit 1
fi

echo "[INFO] Running deterministic bash-script-validator regression suite..."
CI=1 \
VALIDATOR_REQUIRE_SHELLCHECK=1 \
VALIDATOR_SHELLCHECK_MODE=system \
bash "$TEST_SCRIPT"

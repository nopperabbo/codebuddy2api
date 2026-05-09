#!/usr/bin/env bash
#
# CI-friendly regression entrypoint for dockerfile-validator.
# Runs syntax checks, regression tests, and optional ShellCheck linting.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly SKILL_DIR

VALIDATOR_SCRIPT="$SKILL_DIR/scripts/dockerfile-validate.sh"
REGRESSION_SCRIPT="$SKILL_DIR/tests/test_regression.sh"
STRICT_SHELLCHECK="${STRICT_SHELLCHECK:-false}"

echo "Running dockerfile-validator CI checks..."

# Fast syntax guard for scripts used by the regression suite.
bash -n "$VALIDATOR_SCRIPT" "$REGRESSION_SCRIPT" "$0"

# Regression coverage for parser/best-practice branches.
bash "$REGRESSION_SCRIPT"

if command -v shellcheck >/dev/null 2>&1; then
    shellcheck "$VALIDATOR_SCRIPT" "$REGRESSION_SCRIPT" "$0"
    echo "ShellCheck: PASS"
elif [[ "$STRICT_SHELLCHECK" == "true" ]]; then
    echo "ShellCheck: required but not installed (STRICT_SHELLCHECK=true)" >&2
    exit 1
else
    echo "ShellCheck: SKIP (not installed; set STRICT_SHELLCHECK=true to require it)"
fi

echo "PASS: dockerfile-validator CI checks"

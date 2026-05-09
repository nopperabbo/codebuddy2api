#!/usr/bin/env bash
#
# CI-friendly validation entrypoint for terraform-generator feature/version checks.
# Runs:
#   1) shell syntax checks
#   2) feature/version consistency checker
#   3) regression tests for checker fixtures
#   4) optional terraform fmt and shellcheck gates
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

readonly CHECK_SCRIPT="$SCRIPT_DIR/check_feature_version_consistency.sh"
readonly REGRESSION_TEST="$SKILL_DIR/tests/test_feature_version_consistency.sh"
readonly TEMPLATE_VERSIONS_FILE="$SKILL_DIR/assets/minimal-project/versions.tf"
STRICT_SHELLCHECK="${STRICT_SHELLCHECK:-false}"

echo "Running terraform-generator CI checks..."

echo "[1/5] shell syntax checks"
bash -n "$CHECK_SCRIPT" "$REGRESSION_TEST" "$0"

echo "[2/5] feature/version consistency checker"
bash "$CHECK_SCRIPT"

echo "[3/5] regression tests"
bash "$REGRESSION_TEST"

echo "[4/5] terraform fmt (template smoke check)"
if command -v terraform >/dev/null 2>&1; then
    terraform fmt -check "$TEMPLATE_VERSIONS_FILE"
    echo "Terraform fmt: PASS"
else
    echo "Terraform fmt: SKIP (terraform not installed)"
fi

echo "[5/5] shellcheck lint"
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck "$CHECK_SCRIPT" "$REGRESSION_TEST" "$0"
    echo "ShellCheck: PASS"
elif [[ "$STRICT_SHELLCHECK" == "true" ]]; then
    echo "ShellCheck: required but not installed (STRICT_SHELLCHECK=true)" >&2
    exit 1
else
    echo "ShellCheck: SKIP (not installed; set STRICT_SHELLCHECK=true to require it)"
fi

echo "PASS: terraform-generator CI checks"

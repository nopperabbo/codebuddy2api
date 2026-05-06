#!/usr/bin/env bash
#
# Deterministic CI entrypoint for terragrunt-validator.
# Runs syntax checks plus regression tests that do not depend on cloud access.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly SKILL_DIR

VALIDATOR_SCRIPT="$SKILL_DIR/scripts/validate_terragrunt.sh"
DETECTOR_SCRIPT="$SKILL_DIR/scripts/detect_custom_resources.py"
SHELL_REGRESSION_TEST="$SKILL_DIR/test/test_validate_terragrunt.sh"
PYTHON_REGRESSION_TEST="$SKILL_DIR/test/test_detect_custom_resources.py"
SELF_SCRIPT="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"

usage() {
    cat <<'EOF'
Usage: run_ci_checks.sh [OPTIONS]

Deterministic CI checks for terragrunt-validator.

Options:
  --require-shellcheck   Fail when shellcheck is unavailable.
  --skip-shellcheck      Skip shellcheck stage.
  -h, --help             Show this help message.

Environment:
  CI=true|1              Defaults to --require-shellcheck unless overridden.
EOF
}

is_true() {
    local value="${1:-}"
    [[ "$value" == "true" || "$value" == "1" ]]
}

main() {
    local require_shellcheck=0
    local skip_shellcheck=0
    local shellcheck_overridden=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --require-shellcheck)
                require_shellcheck=1
                skip_shellcheck=0
                shellcheck_overridden=1
                ;;
            --skip-shellcheck)
                skip_shellcheck=1
                require_shellcheck=0
                shellcheck_overridden=1
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Error: unknown option '$1'" >&2
                usage
                exit 1
                ;;
        esac
        shift
    done

    if [[ "$shellcheck_overridden" -eq 0 ]] && is_true "${CI:-}"; then
        require_shellcheck=1
    fi

    if [[ "$skip_shellcheck" -eq 1 && "$require_shellcheck" -eq 1 ]]; then
        echo "Error: --skip-shellcheck and --require-shellcheck cannot be combined." >&2
        exit 1
    fi

    export LC_ALL=C
    export LANG=C
    export TZ=UTC

    echo "[1/5] bash syntax checks"
    bash -n "$VALIDATOR_SCRIPT" "$SHELL_REGRESSION_TEST" "$SELF_SCRIPT"

    echo "[2/5] python syntax checks"
    python3 -m py_compile "$DETECTOR_SCRIPT" "$PYTHON_REGRESSION_TEST"

    echo "[3/5] python regression tests"
    python3 "$PYTHON_REGRESSION_TEST"

    echo "[4/5] shell regression tests"
    bash "$SHELL_REGRESSION_TEST"

    echo "[5/5] shellcheck"
    if [[ "$skip_shellcheck" -eq 1 ]]; then
        echo "ShellCheck: SKIP (--skip-shellcheck)"
    elif command -v shellcheck >/dev/null 2>&1; then
        shellcheck "$VALIDATOR_SCRIPT" "$SHELL_REGRESSION_TEST" "$SELF_SCRIPT"
        echo "ShellCheck: PASS"
    elif [[ "$require_shellcheck" -eq 1 ]]; then
        echo "ShellCheck: required but not installed" >&2
        exit 1
    else
        echo "ShellCheck: SKIP (not installed; use --require-shellcheck to enforce)"
    fi

    echo "PASS: terragrunt-validator CI checks"
}

main "$@"

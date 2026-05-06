#!/usr/bin/env bash
#
# Deterministic CI validation entrypoint for bash-script-generator.
# Runs:
#   1) bash -n syntax checks
#   2) shellcheck -x checks (optional or required)
#   3) regression tests (scripts/test_generator.sh)
#

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly TEST_RUNNER="${SCRIPT_DIR}/test_generator.sh"

usage() {
    cat <<EOF
Usage: ${0##*/} [OPTIONS]

Run deterministic checks for bash-script-generator.

Options:
  --require-shellcheck       Fail if shellcheck is unavailable.
  --skip-shellcheck          Skip shellcheck stage.
  --skip-regression-tests    Skip scripts/test_generator.sh.
  -h, --help                 Show this help message.

Environment:
  SHELLCHECK_BIN             Override shellcheck binary/path (default: shellcheck)
  CI=true|1                  Defaults to --require-shellcheck unless explicitly overridden
EOF
}

is_true() {
    local value="$1"
    [[ "$value" == "true" || "$value" == "1" ]]
}

command_is_available() {
    local command_name="$1"
    if [[ "$command_name" == */* ]]; then
        [[ -x "$command_name" ]]
    else
        command -v "$command_name" >/dev/null 2>&1
    fi
}

collect_shell_files() {
    SHELL_FILES=()
    while IFS= read -r file; do
        SHELL_FILES+=("$file")
    done < <(
        {
            find "${SCRIPT_DIR}" -maxdepth 1 -type f -name "*.sh"
            find "${SKILL_DIR}/examples" -maxdepth 1 -type f -name "*.sh"
            find "${SKILL_DIR}/assets/templates" -maxdepth 1 -type f -name "*.sh"
        } | LC_ALL=C sort
    )

    if [[ "${#SHELL_FILES[@]}" -eq 0 ]]; then
        echo "Error: No shell files found to validate." >&2
        return 1
    fi
}

run_syntax_checks() {
    echo "[1/3] bash -n syntax checks"
    local shell_file
    for shell_file in "${SHELL_FILES[@]}"; do
        bash -n "${shell_file}"
    done
    echo "  PASS: bash -n succeeded for ${#SHELL_FILES[@]} file(s)"
}

run_shellcheck_checks() {
    local shellcheck_bin="$1"
    local require_shellcheck="$2"
    local skip_shellcheck="$3"

    if [[ "$skip_shellcheck" -eq 1 ]]; then
        echo "[2/3] shellcheck -x checks"
        echo "  SKIP: shellcheck stage disabled via --skip-shellcheck"
        return 0
    fi

    echo "[2/3] shellcheck -x checks"
    if ! command_is_available "$shellcheck_bin"; then
        if [[ "$require_shellcheck" -eq 1 ]]; then
            echo "Error: shellcheck is required but not available (${shellcheck_bin})." >&2
            return 1
        fi
        echo "  SKIP: shellcheck unavailable (${shellcheck_bin}); continuing without shellcheck"
        return 0
    fi

    local shell_file
    for shell_file in "${SHELL_FILES[@]}"; do
        "$shellcheck_bin" -x "${shell_file}"
    done
    echo "  PASS: shellcheck succeeded for ${#SHELL_FILES[@]} file(s)"
}

run_regression_tests() {
    local skip_regression_tests="$1"

    echo "[3/3] regression tests"
    if [[ "$skip_regression_tests" -eq 1 ]]; then
        echo "  SKIP: regression suite disabled via --skip-regression-tests"
        return 0
    fi

    bash "${TEST_RUNNER}"
}

main() {
    local require_shellcheck=0
    local skip_shellcheck=0
    local skip_regression_tests=0
    local shellcheck_mode_overridden=0
    local shellcheck_bin="${SHELLCHECK_BIN:-shellcheck}"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --require-shellcheck)
                require_shellcheck=1
                skip_shellcheck=0
                shellcheck_mode_overridden=1
                ;;
            --skip-shellcheck)
                skip_shellcheck=1
                require_shellcheck=0
                shellcheck_mode_overridden=1
                ;;
            --skip-regression-tests)
                skip_regression_tests=1
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Error: Unknown option: $1" >&2
                usage
                exit 1
                ;;
        esac
        shift
    done

    if [[ "$shellcheck_mode_overridden" -eq 0 ]] && is_true "${CI:-}"; then
        require_shellcheck=1
    fi

    if [[ "$skip_shellcheck" -eq 1 && "$require_shellcheck" -eq 1 ]]; then
        echo "Error: --skip-shellcheck and --require-shellcheck cannot be used together." >&2
        exit 1
    fi

    export LC_ALL=C
    export LANG=C
    export TZ=UTC

    collect_shell_files
    run_syntax_checks
    run_shellcheck_checks "$shellcheck_bin" "$require_shellcheck" "$skip_shellcheck"
    run_regression_tests "$skip_regression_tests"

    echo ""
    echo "All configured CI checks passed."
}

main "$@"

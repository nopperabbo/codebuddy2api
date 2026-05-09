#!/usr/bin/env bash
#
# Regression test suite for validate.sh
#
# Runs the validator against each example file and asserts the expected exit code.
# Exit 0 when all assertions pass; non-zero otherwise.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
VALIDATOR="$SCRIPT_DIR/validate.sh"
EXAMPLES_DIR="$SCRIPT_DIR/../examples"
TMP_DIR="$(mktemp -d)"
FAKE_SHELLCHECK_BIN="$TMP_DIR/fake-shellcheck-bin"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

# Counters
PASS=0
FAIL=0

# ─── helpers ────────────────────────────────────────────────────────────────

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

# Create a deterministic shellcheck stub so regression tests do not depend on host tooling.
mkdir -p "$FAKE_SHELLCHECK_BIN"
cat > "$FAKE_SHELLCHECK_BIN/shellcheck" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

mode="${FAKE_SHELLCHECK_MODE:-ok}"
target="${@: -1}"

case "$mode" in
    ok)
        exit 0
        ;;
    warning)
        echo "${target}:1:1: warning: fake shellcheck warning [SC9999]"
        exit 1
        ;;
    infra)
        echo "fake shellcheck infrastructure failure" >&2
        exit 3
        ;;
    *)
        echo "unknown FAKE_SHELLCHECK_MODE: $mode" >&2
        exit 2
        ;;
esac
EOF
chmod +x "$FAKE_SHELLCHECK_BIN/shellcheck"

# Run the validator and return its exit code without aborting this script.
# Uses || to prevent set -e from treating a non-zero validator exit as fatal.
run_validator() {
    local file="$1"
    shift

    local exit_code=0
    if [[ $# -gt 0 ]]; then
        env "$@" bash "$VALIDATOR" "$file" >/dev/null 2>&1 || exit_code=$?
    else
        bash "$VALIDATOR" "$file" >/dev/null 2>&1 || exit_code=$?
    fi
    echo "$exit_code"
}

validator_output() {
    local file="$1"
    shift

    if [[ $# -gt 0 ]]; then
        env "$@" bash "$VALIDATOR" "$file" 2>&1 || true
    else
        bash "$VALIDATOR" "$file" 2>&1 || true
    fi
}

# Assert that the validator exits with a specific code for the given file.
assert_exit_code() {
    local label="$1"
    local file="$2"
    local expected="$3"
    shift 3

    local actual
    actual=$(run_validator "$file" "$@")

    if [[ "$actual" -eq "$expected" ]]; then
        pass "$label (exit $actual)"
    else
        fail "$label — expected exit $expected, got $actual"
        # Re-run with output visible so the failure is diagnosable.
        echo "    --- validator output ---"
        validator_output "$file" "$@" | sed 's/^/    /'
        echo "    --- end output ---"
    fi
}

assert_exit_code_in() {
    local label="$1"
    local file="$2"
    local expected_csv="$3"
    shift 3

    local actual
    actual=$(run_validator "$file" "$@")

    if [[ ",$expected_csv," == *",$actual,"* ]]; then
        pass "$label (exit $actual)"
    else
        fail "$label — expected one of [$expected_csv], got $actual"
        echo "    --- validator output ---"
        validator_output "$file" "$@" | sed 's/^/    /'
        echo "    --- end output ---"
    fi
}

# Assert that a pattern IS found in the validator output for a given file.
assert_output_contains() {
    local label="$1"
    local file="$2"
    local pattern="$3"
    shift 3

    local output
    output=$(validator_output "$file" "$@")

    if echo "$output" | grep -qE "$pattern"; then
        pass "$label"
    else
        fail "$label — pattern not found: $pattern"
        echo "    --- validator output ---"
        echo "$output" | sed 's/^/    /'
        echo "    --- end output ---"
    fi
}

# Assert that a pattern is NOT found in the validator output for a given file.
assert_output_not_contains() {
    local label="$1"
    local file="$2"
    local pattern="$3"
    shift 3

    local output
    output=$(validator_output "$file" "$@")

    if echo "$output" | grep -qE "$pattern"; then
        fail "$label — unexpected pattern found: $pattern"
        echo "    --- validator output ---"
        echo "$output" | sed 's/^/    /'
        echo "    --- end output ---"
    else
        pass "$label"
    fi
}

assert_shellcheck_stage_verifiable() {
    local label="$1"
    local file="$2"
    shift 2

    local output
    output=$(validator_output "$file" "$@")

    if ! echo "$output" | grep -q '\[SHELLCHECK\]'; then
        fail "$label — missing [SHELLCHECK] stage"
        echo "    --- validator output ---"
        echo "$output" | sed 's/^/    /'
        echo "    --- end output ---"
        return
    fi

    if echo "$output" | grep -qE 'ShellCheck unavailable|ShellCheck not installed'; then
        fail "$label — ShellCheck stage unavailable"
        echo "    --- validator output ---"
        echo "$output" | sed 's/^/    /'
        echo "    --- end output ---"
        return
    fi

    if echo "$output" | grep -qE 'No ShellCheck issues found|SC[0-9]{4}|: (error|warning|note|style):'; then
        pass "$label"
        return
    fi

    fail "$label — ShellCheck produced no verifiable signal"
    echo "    --- validator output ---"
    echo "$output" | sed 's/^/    /'
    echo "    --- end output ---"
}

# ─── test cases ─────────────────────────────────────────────────────────────

echo "Running bash-script-validator tests..."
echo ""

# --- good-bash.sh: well-written bash, must exit 0 ---
echo "[good-bash.sh]"
assert_exit_code \
    "exits cleanly (code 0)" \
    "$EXAMPLES_DIR/good-bash.sh" \
    0

assert_output_not_contains \
    "no false-positive errors" \
    "$EXAMPLES_DIR/good-bash.sh" \
    "✗"

assert_shellcheck_stage_verifiable \
    "shellcheck stage is verifiable" \
    "$EXAMPLES_DIR/good-bash.sh"

# --- good-shell.sh: well-written POSIX sh, must exit 0 ---
echo ""
echo "[good-shell.sh]"
assert_exit_code \
    "exits cleanly (code 0)" \
    "$EXAMPLES_DIR/good-shell.sh" \
    0

assert_output_not_contains \
    "no false-positive [[ ]] error from comment on line 31" \
    "$EXAMPLES_DIR/good-shell.sh" \
    "\[\["

assert_output_not_contains \
    "no false-positive errors" \
    "$EXAMPLES_DIR/good-shell.sh" \
    "✗"

assert_shellcheck_stage_verifiable \
    "shellcheck stage is verifiable" \
    "$EXAMPLES_DIR/good-shell.sh"

# --- bad-bash.sh: intentionally bad bash, must be non-clean ---
echo ""
echo "[bad-bash.sh]"
assert_exit_code_in \
    "exits non-clean (code 1 or 2)" \
    "$EXAMPLES_DIR/bad-bash.sh" \
    "1,2"

assert_output_contains \
    "detects eval with variable" \
    "$EXAMPLES_DIR/bad-bash.sh" \
    "eval with variable"

assert_output_contains \
    "detects useless cat" \
    "$EXAMPLES_DIR/bad-bash.sh" \
    "Useless use of cat"

# --- bad-shell.sh: intentionally bad POSIX sh, must exit 2 ---
echo ""
echo "[bad-shell.sh]"
assert_exit_code \
    "exits with errors (code 2)" \
    "$EXAMPLES_DIR/bad-shell.sh" \
    2

assert_output_contains \
    "detects [[ ]] in sh script (line 7, actual code)" \
    "$EXAMPLES_DIR/bad-shell.sh" \
    "Bash-specific \[\[ \]\]"

assert_output_contains \
    "detects bash arrays in sh script" \
    "$EXAMPLES_DIR/bad-shell.sh" \
    "Bash-specific arrays"

assert_output_contains \
    "detects function keyword in sh script" \
    "$EXAMPLES_DIR/bad-shell.sh" \
    "function.*keyword"

assert_output_contains \
    "detects source command in sh script" \
    "$EXAMPLES_DIR/bad-shell.sh" \
    "source.*command"

assert_output_contains \
    "detects eval with variable" \
    "$EXAMPLES_DIR/bad-shell.sh" \
    "eval with variable"

assert_output_contains \
    "detects useless cat" \
    "$EXAMPLES_DIR/bad-shell.sh" \
    "Useless use of cat"

# Only real code lines flagged — not comment lines for [[ check
assert_output_not_contains \
    "[[ check does not flag comment lines in bad-shell.sh" \
    "$EXAMPLES_DIR/bad-shell.sh" \
    "Line [0-9]*:# Bad: using bash-specific"

# --- p1 regression fixtures ---
INDENTED_SH="$TMP_DIR/indented-bashisms.sh"
cat > "$INDENTED_SH" <<'EOF'
#!/bin/sh
set -e
    function helper {
        echo "bad"
    }
        source /etc/profile
helper
EOF

COMMENT_ONLY_ERR_HANDLING="$TMP_DIR/comment-only-error-handling.sh"
cat > "$COMMENT_ONLY_ERR_HANDLING" <<'EOF'
#!/bin/sh
# set -e
# set -o errexit
# trap 'echo failed' ERR
echo "hello"
EOF

echo ""
echo "[p1 regressions]"
assert_output_contains \
    "indented function in sh is detected" \
    "$INDENTED_SH" \
    "function.*keyword"

assert_output_contains \
    "indented source in sh is detected" \
    "$INDENTED_SH" \
    "source.*command"

assert_output_contains \
    "comment-only set -e does not suppress warning" \
    "$COMMENT_ONLY_ERR_HANDLING" \
    "Consider adding error handling"

# --- p2 deterministic shellcheck stage regressions ---
echo ""
echo "[p2 shellcheck-mode regressions]"

assert_exit_code \
    "system mode accepts deterministic clean shellcheck run" \
    "$EXAMPLES_DIR/good-bash.sh" \
    0 \
    VALIDATOR_REQUIRE_SHELLCHECK=1 \
    VALIDATOR_SHELLCHECK_MODE=system \
    PATH="$FAKE_SHELLCHECK_BIN:/usr/bin:/bin"

assert_output_contains \
    "system mode reports clean shellcheck output" \
    "$EXAMPLES_DIR/good-bash.sh" \
    "No ShellCheck issues found" \
    VALIDATOR_REQUIRE_SHELLCHECK=1 \
    VALIDATOR_SHELLCHECK_MODE=system \
    PATH="$FAKE_SHELLCHECK_BIN:/usr/bin:/bin"

assert_exit_code \
    "system mode returns warning on shellcheck findings" \
    "$EXAMPLES_DIR/good-bash.sh" \
    1 \
    VALIDATOR_REQUIRE_SHELLCHECK=1 \
    VALIDATOR_SHELLCHECK_MODE=system \
    FAKE_SHELLCHECK_MODE=warning \
    PATH="$FAKE_SHELLCHECK_BIN:/usr/bin:/bin"

assert_output_contains \
    "system mode surfaces shellcheck issue codes" \
    "$EXAMPLES_DIR/good-bash.sh" \
    "SC9999" \
    VALIDATOR_REQUIRE_SHELLCHECK=1 \
    VALIDATOR_SHELLCHECK_MODE=system \
    FAKE_SHELLCHECK_MODE=warning \
    PATH="$FAKE_SHELLCHECK_BIN:/usr/bin:/bin"

assert_exit_code \
    "system mode fails on shellcheck infrastructure error" \
    "$EXAMPLES_DIR/good-bash.sh" \
    2 \
    VALIDATOR_REQUIRE_SHELLCHECK=1 \
    VALIDATOR_SHELLCHECK_MODE=system \
    FAKE_SHELLCHECK_MODE=infra \
    PATH="$FAKE_SHELLCHECK_BIN:/usr/bin:/bin"

assert_output_contains \
    "system mode reports shellcheck infrastructure error" \
    "$EXAMPLES_DIR/good-bash.sh" \
    "ShellCheck execution failed \(exit 3\)" \
    VALIDATOR_REQUIRE_SHELLCHECK=1 \
    VALIDATOR_SHELLCHECK_MODE=system \
    FAKE_SHELLCHECK_MODE=infra \
    PATH="$FAKE_SHELLCHECK_BIN:/usr/bin:/bin"

assert_exit_code \
    "invalid shellcheck mode exits with error" \
    "$EXAMPLES_DIR/good-bash.sh" \
    2 \
    VALIDATOR_SHELLCHECK_MODE=invalid-mode

assert_output_contains \
    "invalid shellcheck mode prints actionable error" \
    "$EXAMPLES_DIR/good-bash.sh" \
    "Invalid VALIDATOR_SHELLCHECK_MODE" \
    VALIDATOR_SHELLCHECK_MODE=invalid-mode

# --- edge cases ---
echo ""
echo "[edge cases]"

# P0: strict mode must fail when ShellCheck is unavailable
assert_exit_code \
    "strict mode fails when shellcheck is unavailable" \
    "$EXAMPLES_DIR/good-bash.sh" \
    2 \
    VALIDATOR_REQUIRE_SHELLCHECK=1 \
    VALIDATOR_DISABLE_SHELLCHECK=1

assert_output_contains \
    "strict mode reports shellcheck unavailable" \
    "$EXAMPLES_DIR/good-bash.sh" \
    "ShellCheck (unavailable|disabled by configuration)" \
    VALIDATOR_REQUIRE_SHELLCHECK=1 \
    VALIDATOR_DISABLE_SHELLCHECK=1

# Missing file → exit 1 from the validator's own error path
assert_exit_code \
    "missing file exits non-zero" \
    "/nonexistent/path/script.sh" \
    1

# ─── summary ────────────────────────────────────────────────────────────────

echo ""
echo "Results: $PASS passed, $FAIL failed"
echo ""

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi

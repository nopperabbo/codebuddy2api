#!/usr/bin/env bash

# Regression tests for scripts/validate_jenkinsfile.sh

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$TEST_DIR/.." && pwd)"
VALIDATOR_SOURCE="$SKILL_DIR/scripts/validate_jenkinsfile.sh"

SANDBOX_ROOT="$(mktemp -d)"
trap 'rm -rf "$SANDBOX_ROOT"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
TEST_OUTPUT=""
TEST_STATUS=0

prepare_sandbox() {
    local name=$1
    local sandbox="$SANDBOX_ROOT/$name"

    mkdir -p "$sandbox/skill/scripts" "$sandbox/work"
    cp "$SKILL_DIR/scripts/"*.sh "$sandbox/skill/scripts/"
    chmod +x "$sandbox/skill/scripts/"*.sh

    echo "$sandbox"
}

strip_ansi() {
    printf '%s\n' "$1" | sed 's/\x1b\[[0-9;]*m//g'
}

run_validator() {
    local sandbox=$1
    shift
    local args=("$@")

    set +e
    TEST_OUTPUT=$(bash "$sandbox/skill/scripts/validate_jenkinsfile.sh" "${args[@]}" 2>&1)
    TEST_STATUS=$?
    set -e
}

pass() {
    local message=$1
    echo "PASS: $message"
    PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
    local message=$1
    echo "FAIL: $message"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

assert_exit() {
    local message=$1
    local expected=$2
    if [ "$TEST_STATUS" -eq "$expected" ]; then
        pass "$message"
    else
        fail "$message (expected exit $expected, got $TEST_STATUS)"
    fi
}

assert_contains() {
    local message=$1
    local pattern=$2
    if strip_ansi "$TEST_OUTPUT" | grep -Eq "$pattern"; then
        pass "$message"
    else
        fail "$message (pattern not found: $pattern)"
    fi
}

assert_not_contains() {
    local message=$1
    local pattern=$2
    if strip_ansi "$TEST_OUTPUT" | grep -Eq "$pattern"; then
        fail "$message (unexpected pattern found: $pattern)"
    else
        pass "$message"
    fi
}

assert_equals() {
    local message=$1
    local expected=$2
    local actual=$3
    if [ "$expected" = "$actual" ]; then
        pass "$message"
    else
        fail "$message (expected: $expected, actual: $actual)"
    fi
}

if [ ! -f "$VALIDATOR_SOURCE" ]; then
    echo "ERROR: validator script not found at $VALIDATOR_SOURCE"
    exit 1
fi

echo "Running validate_jenkinsfile.sh regression tests..."

# Test 1: Unknown/non-pipeline files fail closed by default.
sandbox="$(prepare_sandbox "unknown_fail_closed")"
cat > "$sandbox/work/not-a-jenkinsfile.groovy" <<'EOF'
println "hello from groovy"
def x = 1 + 2
EOF

run_validator "$sandbox" --syntax-only "$sandbox/work/not-a-jenkinsfile.groovy"
assert_exit "unknown file exits with validation failure" 1
assert_contains "reports type detection failure" "ERROR \\[TypeDetection\\]: Unable to classify file as Declarative or Scripted pipeline\\."
assert_contains "prints unknown marker guidance" "HINT: no pipeline markers detected\\."
assert_not_contains "does not report validation passed" "VALIDATION PASSED"

# Test 2: Unknown type override is explicit and bypasses type-detection failure.
run_validator "$sandbox" --syntax-only --assume-scripted "$sandbox/work/not-a-jenkinsfile.groovy"
assert_contains "assume flag marks scripted mode as assumed" "Pipeline type: Scripted \\(assumed\\)"
assert_not_contains "assume flag avoids type-detection error" "ERROR \\[TypeDetection\\]"

# Test 3: Missing child validator reports exactly one runner error (no double count).
sandbox="$(prepare_sandbox "runner_error_count")"
cat > "$sandbox/work/declarative.Jenkinsfile" <<'EOF'
pipeline {
  agent any
  stages {
    stage('Build') {
      steps {
        echo 'Hello'
      }
    }
  }
}
EOF
rm -f "$sandbox/skill/scripts/validate_declarative.sh"

run_validator "$sandbox" --syntax-only "$sandbox/work/declarative.Jenkinsfile"
assert_exit "missing declarative validator exits with validation failure" 1
assert_contains "runner error line is emitted" "^ERROR \\[Runner\\]: Required script is missing or not readable: validate_declarative\\.sh$"
assert_contains "syntax summary reports single error" "Syntax validation failed with 1 error\\(s\\)"
runner_error_count="$(strip_ansi "$TEST_OUTPUT" | grep -E -c '^ERROR \[Runner\]:' || true)"
assert_equals "runner error appears once in output" "1" "$runner_error_count"

echo ""
echo "Test summary: $PASS_COUNT passed, $FAIL_COUNT failed"

if [ "$FAIL_COUNT" -ne 0 ]; then
    exit 1
fi

echo "PASS: validate_jenkinsfile.sh regression tests"

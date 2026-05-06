#!/usr/bin/env bash
#
# Regression tests for dockerfile-generator scripts and examples.
#
# Covers:
#   1. Node/Python structured entrypoint args (--entry-cmd/--entry-arg)
#   2. Legacy --entry behavior and quote rejection
#   3. Node multistage example dependency/build flow consistency
#
# Exit 0 when all assertions pass; non-zero otherwise.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly NODE_GENERATOR="$SCRIPT_DIR/generate_nodejs.sh"
readonly PYTHON_GENERATOR="$SCRIPT_DIR/generate_python.sh"
readonly NODE_EXAMPLE="$SKILL_DIR/examples/nodejs-multistage.Dockerfile"

PASS=0
FAIL=0
OUTPUT=""
EXIT_CODE=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

run_capture() {
    EXIT_CODE=0
    OUTPUT=$("$@" 2>&1) || EXIT_CODE=$?
}

assert_exit() {
    local label="$1"
    local expected="$2"
    if [[ "$EXIT_CODE" -eq "$expected" ]]; then
        pass "$label (exit $EXIT_CODE)"
    else
        fail "$label — expected exit $expected, got $EXIT_CODE"
        echo "$OUTPUT" | sed 's/^/    /'
    fi
}

assert_output_contains() {
    local label="$1"
    local pattern="$2"
    if echo "$OUTPUT" | grep -qE -- "$pattern"; then
        pass "$label"
    else
        fail "$label — pattern not found: $pattern"
        echo "$OUTPUT" | sed 's/^/    /'
    fi
}

assert_file_contains() {
    local label="$1"
    local file="$2"
    local pattern="$3"
    if grep -qE -- "$pattern" "$file"; then
        pass "$label"
    else
        fail "$label — pattern '$pattern' not found in $file"
        sed 's/^/    /' "$file"
    fi
}

assert_file_not_contains() {
    local label="$1"
    local file="$2"
    local pattern="$3"
    if grep -qE -- "$pattern" "$file"; then
        fail "$label — unexpected pattern '$pattern' found in $file"
        grep -nE -- "$pattern" "$file" | sed 's/^/    /'
    else
        pass "$label"
    fi
}

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Running dockerfile-generator regression tests..."

echo ""
echo "[shell syntax checks]"
if bash -n "$NODE_GENERATOR"; then
    pass "node generator passes bash -n"
else
    fail "node generator has syntax errors"
fi

if bash -n "$PYTHON_GENERATOR"; then
    pass "python generator passes bash -n"
else
    fail "python generator has syntax errors"
fi

echo ""
echo "[node generator]"
NODE_STRUCTURED_OUT="$TMP_DIR/node-structured.Dockerfile"
run_capture \
    bash "$NODE_GENERATOR" \
    --output "$NODE_STRUCTURED_OUT" \
    --entry-cmd node \
    --entry-arg server.js \
    --entry-arg --message \
    --entry-arg "hello world"
assert_exit "structured node entry generation succeeds" 0
assert_file_contains \
    "structured node entry preserves spaced arg" \
    "$NODE_STRUCTURED_OUT" \
    'CMD \["node","server\.js","--message","hello world"\]'

NODE_LEGACY_OUT="$TMP_DIR/node-legacy.Dockerfile"
run_capture \
    bash "$NODE_GENERATOR" \
    --output "$NODE_LEGACY_OUT" \
    --entry "npm start"
assert_exit "legacy node entry generation succeeds" 0
assert_file_contains \
    "legacy node entry still tokenizes simple commands" \
    "$NODE_LEGACY_OUT" \
    'CMD \["npm","start"\]'

run_capture \
    bash "$NODE_GENERATOR" \
    --output "$TMP_DIR/node-legacy-quoted.Dockerfile" \
    --entry "node server.js --message \"hello world\""
assert_exit "legacy quoted node entry is rejected" 1
assert_output_contains \
    "legacy quoted node rejection message is clear" \
    'ERROR: quoted --entry values are not supported\. Use --entry-cmd/--entry-arg\.'

run_capture \
    bash "$NODE_GENERATOR" \
    --output "$TMP_DIR/node-invalid-args.Dockerfile" \
    --entry-arg server.js
assert_exit "--entry-arg without --entry-cmd fails for node" 1
assert_output_contains \
    "node --entry-arg validation message is clear" \
    'ERROR: --entry-arg requires --entry-cmd\.'

echo ""
echo "[python generator]"
PY_STRUCTURED_OUT="$TMP_DIR/python-structured.Dockerfile"
run_capture \
    bash "$PYTHON_GENERATOR" \
    --output "$PY_STRUCTURED_OUT" \
    --entry-cmd python \
    --entry-arg -m \
    --entry-arg uvicorn \
    --entry-arg main:app \
    --entry-arg --log-config \
    --entry-arg "configs/logging prod.yaml"
assert_exit "structured python entry generation succeeds" 0
assert_file_contains \
    "structured python entry preserves spaced arg" \
    "$PY_STRUCTURED_OUT" \
    'CMD \["python","-m","uvicorn","main:app","--log-config","configs/logging prod\.yaml"\]'

PY_LEGACY_OUT="$TMP_DIR/python-legacy.Dockerfile"
run_capture \
    bash "$PYTHON_GENERATOR" \
    --output "$PY_LEGACY_OUT" \
    --entry "python app.py"
assert_exit "legacy python entry generation succeeds" 0
assert_file_contains \
    "legacy python entry still tokenizes simple commands" \
    "$PY_LEGACY_OUT" \
    'CMD \["python","app\.py"\]'

run_capture \
    bash "$PYTHON_GENERATOR" \
    --output "$TMP_DIR/python-legacy-quoted.Dockerfile" \
    --entry "python app.py --message \"hello world\""
assert_exit "legacy quoted python entry is rejected" 1
assert_output_contains \
    "legacy quoted python rejection message is clear" \
    'ERROR: quoted --entry values are not supported\. Use --entry-cmd/--entry-arg\.'

echo ""
echo "[node example]"
assert_file_contains \
    "node example installs full deps before build" \
    "$NODE_EXAMPLE" \
    'RUN npm ci &&'
assert_file_contains \
    "node example prunes dev dependencies after build" \
    "$NODE_EXAMPLE" \
    'npm prune --omit=dev'
assert_file_not_contains \
    "node example avoids mixed only=production build flow" \
    "$NODE_EXAMPLE" \
    'npm ci --only=production'
assert_file_contains \
    "node example runs compiled output" \
    "$NODE_EXAMPLE" \
    'CMD \["node", "dist/index\.js"\]'

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi

echo "All dockerfile-generator regression tests passed."

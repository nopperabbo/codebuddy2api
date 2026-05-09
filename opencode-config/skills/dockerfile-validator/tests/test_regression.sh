#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR="$SKILL_DIR/scripts/dockerfile-validate.sh"
FIXTURES_DIR="$SKILL_DIR/tests/fixtures"
TMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

PASS=0
FAIL=0

pass() {
    echo "  PASS: $1"
    PASS=$((PASS + 1))
}

fail() {
    echo "  FAIL: $1"
    FAIL=$((FAIL + 1))
}

make_stub_tools() {
    mkdir -p "$TMP_DIR/bin"

    cat > "$TMP_DIR/bin/hadolint" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF

    cat > "$TMP_DIR/bin/checkov" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF

    chmod +x "$TMP_DIR/bin/hadolint" "$TMP_DIR/bin/checkov"
}

validator_output() {
    local dockerfile="$1"
    PATH="$TMP_DIR/bin:$PATH" bash "$VALIDATOR" "$dockerfile" 2>&1 || true
}

validator_exit_code() {
    local dockerfile="$1"
    local exit_code=0
    PATH="$TMP_DIR/bin:$PATH" bash "$VALIDATOR" "$dockerfile" >/dev/null 2>&1 || exit_code=$?
    echo "$exit_code"
}

assert_output_contains() {
    local label="$1"
    local dockerfile="$2"
    local pattern="$3"

    local output
    output="$(validator_output "$dockerfile")"

    if echo "$output" | grep -qE "$pattern"; then
        pass "$label"
    else
        fail "$label (missing pattern: $pattern)"
        echo "    --- validator output ---"
        echo "$output" | sed 's/^/    /'
        echo "    --- end output ---"
    fi
}

assert_output_not_contains() {
    local label="$1"
    local dockerfile="$2"
    local pattern="$3"

    local output
    output="$(validator_output "$dockerfile")"

    if echo "$output" | grep -qE "$pattern"; then
        fail "$label (unexpected pattern: $pattern)"
        echo "    --- validator output ---"
        echo "$output" | sed 's/^/    /'
        echo "    --- end output ---"
    else
        pass "$label"
    fi
}

assert_exit_zero() {
    local label="$1"
    local dockerfile="$2"

    local exit_code
    exit_code="$(validator_exit_code "$dockerfile")"

    if [[ "$exit_code" -eq 0 ]]; then
        pass "$label"
    else
        fail "$label (expected 0, got $exit_code)"
    fi
}

echo "Running dockerfile-validator regression tests..."
echo ""

make_stub_tools

COPY_BEFORE_YARN="$FIXTURES_DIR/copy-before-yarn.Dockerfile"
COPY_BEFORE_YARN_LOCK="$FIXTURES_DIR/copy-before-yarn-lock-read.Dockerfile"
FROM_PLATFORM_NONROOT="$FIXTURES_DIR/from-platform-nonroot.Dockerfile"

echo "[copy-before-yarn]"
assert_output_contains \
    "flags COPY . before bare RUN yarn" \
    "$COPY_BEFORE_YARN" \
    "COPY \\. appears before dependency installation"
assert_exit_zero \
    "warn-only result stays non-failing" \
    "$COPY_BEFORE_YARN"

echo ""
echo "[copy-before-yarn-lock-read]"
assert_output_not_contains \
    "does not misclassify yarn.lock as yarn install" \
    "$COPY_BEFORE_YARN_LOCK" \
    "COPY \\. appears before dependency installation"
assert_exit_zero \
    "non-install RUN after COPY . remains non-failing" \
    "$COPY_BEFORE_YARN_LOCK"

echo ""
echo "[from-platform-nonroot]"
assert_output_contains \
    "parses --platform final image as non-root base" \
    "$FROM_PLATFORM_NONROOT" \
    "No USER directive, but final base image is non-root: gcr.io/distroless/static-debian11:nonroot"
assert_output_not_contains \
    "does not emit root warning for non-root distroless base" \
    "$FROM_PLATFORM_NONROOT" \
    "container will run as root"
assert_output_contains \
    "optimization stage reports parsed minimal final base" \
    "$FROM_PLATFORM_NONROOT" \
    "Using minimal base for final stage: gcr.io/distroless/static-debian11:nonroot"
assert_output_not_contains \
    "base image analysis never treats --platform as image" \
    "$FROM_PLATFORM_NONROOT" \
    "Consider Alpine alternative for: --platform"
assert_exit_zero \
    "platform flag fixture exits successfully" \
    "$FROM_PLATFORM_NONROOT"

echo ""
echo "Summary: $PASS passed, $FAIL failed"

if [[ "$FAIL" -ne 0 ]]; then
    exit 1
fi

echo "PASS: dockerfile-validator regression tests"

#!/usr/bin/env bash
#
# Regression test suite for scripts/validate_workflow.sh
#
# Covers:
# - P0: no false-success when actionlint is missing and act cannot validate target
# - P1: advisory policy checks (SHA pinning, permissions, script injection, OIDC)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly SKILL_DIR
VALIDATOR_SOURCE="$SKILL_DIR/scripts/validate_workflow.sh"
readonly VALIDATOR_SOURCE

TMP_ROOT="$(mktemp -d)"
cleanup() {
    rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

PASS=0
FAIL=0
OUTPUT=""
EXIT_CODE=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

new_sandbox() {
    SANDBOX="$(mktemp -d "$TMP_ROOT/case-XXXXXX")"

    mkdir -p "$SANDBOX/skill/scripts/.tools"
    mkdir -p "$SANDBOX/repo/.github/workflows"
    mkdir -p "$SANDBOX/repo/examples"
    mkdir -p "$SANDBOX/bin"

    cp "$VALIDATOR_SOURCE" "$SANDBOX/skill/scripts/validate_workflow.sh"
    chmod +x "$SANDBOX/skill/scripts/validate_workflow.sh"

    cat > "$SANDBOX/bin/docker" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "info" ]]; then
    exit "${DOCKER_INFO_STUB_EXIT:-0}"
fi
exit 0
EOF
    chmod +x "$SANDBOX/bin/docker"
}

create_act_stub() {
    cat > "$SANDBOX/skill/scripts/.tools/act" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *"--list"* ]]; then
    exit "${ACT_LIST_STUB_EXIT:-0}"
fi
if [[ "$*" == *"--dryrun"* ]]; then
    exit "${ACT_DRYRUN_STUB_EXIT:-0}"
fi
exit "${ACT_STUB_EXIT:-0}"
EOF
    chmod +x "$SANDBOX/skill/scripts/.tools/act"
}

create_actionlint_stub() {
    cat > "$SANDBOX/skill/scripts/.tools/actionlint" <<'EOF'
#!/usr/bin/env bash
exit "${ACTIONLINT_STUB_EXIT:-0}"
EOF
    chmod +x "$SANDBOX/skill/scripts/.tools/actionlint"
}

run_validator() {
    local -a args=("$@")
    OUTPUT=""
    EXIT_CODE=0
    OUTPUT=$(
        cd "$SANDBOX/repo" && \
        PATH="$SANDBOX/bin:$PATH" bash "$SANDBOX/skill/scripts/validate_workflow.sh" "${args[@]}" 2>&1
    ) || EXIT_CODE=$?
}

assert_exit() {
    local label="$1"
    local expected="$2"
    if [[ "$EXIT_CODE" -eq "$expected" ]]; then
        pass "$label (exit $EXIT_CODE)"
    else
        fail "$label (expected exit $expected, got $EXIT_CODE)"
        echo "$OUTPUT" | sed 's/^/    /'
    fi
}

assert_contains() {
    local label="$1"
    local pattern="$2"
    if echo "$OUTPUT" | grep -qE "$pattern"; then
        pass "$label"
    else
        fail "$label (pattern not found: $pattern)"
        echo "$OUTPUT" | sed 's/^/    /'
    fi
}

assert_not_contains() {
    local label="$1"
    local pattern="$2"
    if echo "$OUTPUT" | grep -qE "$pattern"; then
        fail "$label (unexpected pattern found: $pattern)"
        echo "$OUTPUT" | sed 's/^/    /'
    else
        pass "$label"
    fi
}

echo "Running github-actions-validator regression tests..."
echo ""

echo "[P0] actionlint missing + target outside .github/workflows must fail"
new_sandbox
create_act_stub
cat > "$SANDBOX/repo/examples/outside.yml" <<'EOF'
name: Outside
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
EOF
run_validator "$SANDBOX/repo/examples/outside.yml"
if [[ "$EXIT_CODE" -ne 0 ]]; then
    pass "returns non-zero when no effective validator executed"
else
    fail "returns non-zero when no effective validator executed (expected non-zero, got 0)"
    echo "$OUTPUT" | sed 's/^/    /'
fi
assert_contains "reports skipped act path" "act validation skipped"
assert_contains "reports no effective validator" "No effective validator executed|No validator executed; refusing to report success"

echo ""
echo "[P0] actionlint run + act skip should still pass"
new_sandbox
create_act_stub
create_actionlint_stub
cat > "$SANDBOX/repo/examples/outside.yml" <<'EOF'
name: Outside
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
EOF
run_validator "$SANDBOX/repo/examples/outside.yml"
assert_exit "passes when actionlint runs and act skips unsupported target" 0
assert_contains "shows actionlint success" "actionlint validation passed"
assert_contains "shows act skip message" "act validation skipped: target file is outside \\.github/workflows"

echo ""
echo "[P0] fallback to act-only still works for real workflow paths"
new_sandbox
create_act_stub
cat > "$SANDBOX/repo/.github/workflows/ci.yml" <<'EOF'
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
EOF
run_validator "$SANDBOX/repo/.github/workflows/ci.yml"
assert_exit "passes in act-only fallback mode for workflow under .github/workflows" 0
assert_contains "warns about actionlint fallback" "actionlint not found\\. Falling back to act-only validation"
assert_contains "act dry-run success is reported" "act validation passed"

echo ""
echo "[P1] policy checks report hardening warnings (advisory)"
new_sandbox
create_actionlint_stub
cat > "$SANDBOX/repo/examples/policy-bad.yml" <<'EOF'
name: Policy Bad
on: pull_request
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: docker/build-push-action@v6
      - uses: aws-actions/configure-aws-credentials@v4
      - name: Unsafe run usage
        run: echo "${{ github.event.pull_request.title }}"
EOF
run_validator --lint-only --policy-checks "$SANDBOX/repo/examples/policy-bad.yml"
assert_exit "policy warnings do not change exit code" 0
assert_contains "warns for unpinned third-party action" "third-party action is not SHA pinned: docker/build-push-action@v6"
assert_contains "warns for missing permissions" "missing explicit permissions block"
assert_contains "warns for script injection pattern" "potential script injection risk in run step"
assert_contains "warns for missing id-token with OIDC action" "OIDC-related action but does not declare id-token: write"
assert_contains "prints policy warning summary" "Security policy warnings:"

echo ""
echo "[P1] policy checks accept hardened workflow"
new_sandbox
create_actionlint_stub
cat > "$SANDBOX/repo/examples/policy-good.yml" <<'EOF'
name: Policy Good
on: pull_request
permissions:
  contents: read
  id-token: write
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: docker/build-push-action@0123456789abcdef0123456789abcdef01234567
      - uses: aws-actions/configure-aws-credentials@0123456789abcdef0123456789abcdef01234567
      - name: Safe run usage
        env:
          PR_TITLE: ${{ github.event.pull_request.title }}
        run: echo "$PR_TITLE"
EOF
run_validator --lint-only --policy-checks "$SANDBOX/repo/examples/policy-good.yml"
assert_exit "hardened workflow remains successful" 0
assert_contains "prints clean policy summary" "No security policy warnings found"
assert_not_contains "does not print warning summary when clean" "Security policy warnings:"

echo ""
echo "Test summary: PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -ne 0 ]]; then
    exit 1
fi

echo "All tests passed."

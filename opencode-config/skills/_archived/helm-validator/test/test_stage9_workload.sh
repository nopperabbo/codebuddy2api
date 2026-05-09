#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CHART_DIR="$SKILL_DIR/test/test-workload-chart"
PINNED_VALUES="$CHART_DIR/values-pinned-tag.yaml"

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

assert_contains() {
    local label="$1"
    local file="$2"
    local pattern="$3"
    if grep -Eq "$pattern" "$file"; then
        pass "$label"
    else
        fail "$label (missing pattern: $pattern)"
    fi
}

assert_not_contains() {
    local label="$1"
    local file="$2"
    local pattern="$3"
    if grep -Eq "$pattern" "$file"; then
        fail "$label (unexpected pattern: $pattern)"
    else
        pass "$label"
    fi
}

if ! command -v helm >/dev/null 2>&1; then
    echo "FAIL: helm is required for test_stage9_workload.sh"
    exit 1
fi

echo "Running helm-validator Stage 9 workload regression checks..."
echo ""

DEFAULT_OUT="$TMP_DIR/default"
PINNED_OUT="$TMP_DIR/pinned"
mkdir -p "$DEFAULT_OUT" "$PINNED_OUT"

helm template stage9-default "$CHART_DIR" --output-dir "$DEFAULT_OUT" >/dev/null
helm template stage9-pinned "$CHART_DIR" --values "$PINNED_VALUES" --output-dir "$PINNED_OUT" >/dev/null

DEFAULT_DEPLOYMENT="$(find "$DEFAULT_OUT" -type f -name "deployment.yaml" | head -n 1)"
PINNED_DEPLOYMENT="$(find "$PINNED_OUT" -type f -name "deployment.yaml" | head -n 1)"

if [[ -z "$DEFAULT_DEPLOYMENT" || -z "$PINNED_DEPLOYMENT" ]]; then
    echo "FAIL: rendered deployment manifest not found"
    exit 1
fi

echo "[default values]"
assert_contains "flags :latest image tag in default fixture" "$DEFAULT_DEPLOYMENT" 'image:[[:space:]]*"?nginx:latest"?'
assert_not_contains "default fixture omits pod/container securityContext" "$DEFAULT_DEPLOYMENT" 'securityContext:'
assert_not_contains "default fixture omits resources block" "$DEFAULT_DEPLOYMENT" 'resources:'
assert_not_contains "default fixture omits livenessProbe" "$DEFAULT_DEPLOYMENT" 'livenessProbe:'
assert_not_contains "default fixture omits readinessProbe" "$DEFAULT_DEPLOYMENT" 'readinessProbe:'

echo ""
echo "[pinned image override]"
assert_not_contains "pinned values remove :latest image tag" "$PINNED_DEPLOYMENT" 'image:[[:space:]]*"?[^"]*:latest"?'
assert_contains "pinned values render explicit pinned tag" "$PINNED_DEPLOYMENT" 'image:[[:space:]]*"?nginx:1\.27\.2"?'
assert_not_contains "other Stage 9 omissions remain for pinned profile" "$PINNED_DEPLOYMENT" 'securityContext:'

echo ""
echo "Stage 9 summary: PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -ne 0 ]]; then
    exit 1
fi

echo "PASS: Stage 9 workload regression checks"

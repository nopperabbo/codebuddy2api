#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DETECT_CRD_WRAPPER="$SKILL_DIR/scripts/detect_crd_wrapper.sh"
STRUCTURE_VALIDATOR="$SKILL_DIR/scripts/validate_chart_structure.sh"
STAGE9_TEST="$SKILL_DIR/test/test_stage9_workload.sh"
CRD_README="$SKILL_DIR/test/test-crd-chart/README.md"

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

assert_file_contains() {
    local label="$1"
    local file="$2"
    local pattern="$3"
    if grep -Eq "$pattern" "$file"; then
        pass "$label"
    else
        fail "$label (missing pattern: $pattern)"
        echo "    file: $file"
    fi
}

assert_file_not_contains() {
    local label="$1"
    local file="$2"
    local pattern="$3"
    if grep -Eq "$pattern" "$file"; then
        fail "$label (unexpected pattern: $pattern)"
        echo "    file: $file"
    else
        pass "$label"
    fi
}

assert_exit_code() {
    local label="$1"
    local expected="$2"
    local actual="$3"
    if [[ "$actual" -eq "$expected" ]]; then
        pass "$label"
    else
        fail "$label (expected $expected, got $actual)"
    fi
}

echo "Running helm-validator regression tests..."
echo ""

echo "[P0] detect_crd.py parse-first template detection"
LITERAL_YAML="$TMP_DIR/literal-braces.yaml"
cat > "$LITERAL_YAML" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: literal-braces
data:
  token: "{{username}}"
EOF

set +e
bash "$DETECT_CRD_WRAPPER" "$LITERAL_YAML" > "$TMP_DIR/literal.json" 2> "$TMP_DIR/literal.err"
rc=$?
set -e
assert_exit_code "valid YAML with literal braces exits zero" 0 "$rc"
assert_file_contains "valid literal braces manifest is parsed as ConfigMap" "$TMP_DIR/literal.json" '"kind":[[:space:]]*"ConfigMap"'
assert_file_not_contains "valid literal braces manifest does not emit unrendered-template error" "$TMP_DIR/literal.err" "unrendered Helm template"

UNRENDERED_YAML="$TMP_DIR/unrendered-template.yaml"
cat > "$UNRENDERED_YAML" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Values.name }}
data:
  token: "example"
EOF

set +e
bash "$DETECT_CRD_WRAPPER" "$UNRENDERED_YAML" > "$TMP_DIR/unrendered.json" 2> "$TMP_DIR/unrendered.err"
rc=$?
set -e
if [[ "$rc" -ne 0 ]]; then
    pass "unrendered Helm template exits non-zero"
else
    fail "unrendered Helm template exits non-zero (expected non-zero, got 0)"
fi
assert_file_contains "unrendered Helm template returns actionable error" "$TMP_DIR/unrendered.err" "appears to be an unrendered Helm template"

echo ""
echo "[P1] validate_chart_structure.sh parser fallback (no yq)"
CHART_DIR="$TMP_DIR/commented-chart"
mkdir -p "$CHART_DIR/templates" "$TMP_DIR/bin"

cat > "$CHART_DIR/Chart.yaml" <<'EOF'
apiVersion: v2 # inline comment should not affect parsing
name: "commented-chart" # quoted value must parse cleanly
version: "0.1.0" # trailing comment
EOF

cat > "$CHART_DIR/values.yaml" <<'EOF'
replicaCount: 1
EOF

cat > "$CHART_DIR/templates/configmap.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: commented-chart
EOF

cat > "$TMP_DIR/bin/yamllint" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
chmod +x "$TMP_DIR/bin/yamllint"

set +e
PATH="$TMP_DIR/bin:/usr/bin:/bin" bash "$STRUCTURE_VALIDATOR" "$CHART_DIR" > "$TMP_DIR/structure.out" 2>&1
rc=$?
set -e
assert_exit_code "chart structure check succeeds without yq" 0 "$rc"
assert_file_not_contains "apiVersion warning is not falsely triggered by inline comment" "$TMP_DIR/structure.out" "apiVersion should be 'v2'"
assert_file_not_contains "apiVersion is not reported as missing" "$TMP_DIR/structure.out" "missing 'apiVersion'"
assert_file_not_contains "name is not reported as missing" "$TMP_DIR/structure.out" "missing 'name'"
assert_file_not_contains "version is not reported as missing" "$TMP_DIR/structure.out" "missing 'version'"

echo ""
echo "[P2] CRD docs URL pinning"
assert_file_not_contains "cert-manager URL is not using releases/latest" "$CRD_README" "releases/latest/download/cert-manager.yaml"
assert_file_contains "cert-manager URL is pinned to releases/download/<version>" "$CRD_README" "releases/download/v[0-9]+\\.[0-9]+\\.[0-9]+/cert-manager\\.yaml"

echo ""
echo "[P1] Stage 9 workload harness"
set +e
bash "$STAGE9_TEST" > "$TMP_DIR/stage9.out" 2>&1
rc=$?
set -e
if [[ "$rc" -eq 0 ]]; then
    pass "Stage 9 workload harness passes"
else
    fail "Stage 9 workload harness passes (expected 0, got $rc)"
    echo "    --- stage9 output ---"
    sed 's/^/    /' "$TMP_DIR/stage9.out"
    echo "    --- end stage9 output ---"
fi

echo ""
echo "Regression summary: PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -ne 0 ]]; then
    exit 1
fi

echo "PASS: helm-validator regression tests"

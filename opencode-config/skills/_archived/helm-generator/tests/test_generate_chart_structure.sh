#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GENERATOR_SCRIPT="$SKILL_DIR/scripts/generate_chart_structure.sh"
SCHEMA_FILE="$SKILL_DIR/assets/values-schema-template.json"

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

run_expect_success() {
  local label="$1"
  shift
  local log_file="$TMP_DIR/success_${PASS}_${FAIL}.log"

  set +e
  "$@" >"$log_file" 2>&1
  local rc=$?
  set -e

  if [[ $rc -eq 0 ]]; then
    pass "$label"
  else
    fail "$label (exit $rc)"
    sed 's/^/    /' "$log_file"
  fi
}

run_expect_failure() {
  local label="$1"
  shift
  local log_file="$TMP_DIR/failure_${PASS}_${FAIL}.log"

  set +e
  "$@" >"$log_file" 2>&1
  local rc=$?
  set -e

  if [[ $rc -ne 0 ]]; then
    pass "$label"
  else
    fail "$label (unexpected success)"
  fi
}

assert_file_contains_literal() {
  local label="$1"
  local file_path="$2"
  local expected_text="$3"

  if grep -Fq -- "$expected_text" "$file_path"; then
    pass "$label"
  else
    fail "$label (missing '$expected_text' in $file_path)"
  fi
}

if ! command -v helm >/dev/null 2>&1; then
  echo "FAIL: helm CLI is required for this regression suite"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: python3 is required for schema assertions"
  exit 1
fi

VALID_SHA256_HASH="94a00394bc5a8ef503fb59db0a7d0ae9e1119866e8aee8ba40cd864cea69ea1a"
VALID_SHA512_HASH=""
for _ in {1..128}; do
  VALID_SHA512_HASH="${VALID_SHA512_HASH}a"
done

CHART_ROOT="$TMP_DIR/charts"
mkdir -p "$CHART_ROOT"

echo "[1] Digest validation"
run_expect_failure \
  "reject empty sha256 hash" \
  bash "$GENERATOR_SCRIPT" invaliddigestempty "$CHART_ROOT" \
  --image "ghcr.io/acme/api@sha256:" --force

run_expect_failure \
  "reject short sha256 hash" \
  bash "$GENERATOR_SCRIPT" invaliddigestshort "$CHART_ROOT" \
  --image "ghcr.io/acme/api@sha256:abcd" --force

run_expect_failure \
  "reject non-hex sha256 hash" \
  bash "$GENERATOR_SCRIPT" invaliddigesthex "$CHART_ROOT" \
  --image "ghcr.io/acme/api@sha256:zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz" --force

run_expect_failure \
  "reject unsupported digest algorithm" \
  bash "$GENERATOR_SCRIPT" invaliddigestalgo "$CHART_ROOT" \
  --image "ghcr.io/acme/api@md5:0123456789abcdef0123456789abcdef" --force

run_expect_success \
  "accept valid sha256 digest" \
  bash "$GENERATOR_SCRIPT" digestoksha256 "$CHART_ROOT" \
  --image "ghcr.io/acme/api@sha256:${VALID_SHA256_HASH}" --with-templates --force

run_expect_success \
  "accept valid sha512 digest" \
  bash "$GENERATOR_SCRIPT" digestoksha512 "$CHART_ROOT" \
  --image "ghcr.io/acme/api@sha512:${VALID_SHA512_HASH}" --force

SHA256_VALUES="$CHART_ROOT/digestoksha256/values.yaml"
SHA512_VALUES="$CHART_ROOT/digestoksha512/values.yaml"
assert_file_contains_literal "sha256 digest written to values.yaml" "$SHA256_VALUES" "  digest: \"sha256:${VALID_SHA256_HASH}\""
assert_file_contains_literal "sha512 digest written to values.yaml" "$SHA512_VALUES" "  digest: \"sha512:${VALID_SHA512_HASH}\""
assert_file_contains_literal "digest chart keeps tag empty" "$SHA256_VALUES" "  tag: \"\""

echo "[2] Tag and digest conflict handling"
run_expect_failure \
  "reject digest image with explicit --tag" \
  bash "$GENERATOR_SCRIPT" digesttagflag "$CHART_ROOT" \
  --image "ghcr.io/acme/api@sha256:${VALID_SHA256_HASH}" --tag "1.2.3" --force

run_expect_failure \
  "reject image refs containing both tag and digest" \
  bash "$GENERATOR_SCRIPT" digesttaginline "$CHART_ROOT" \
  --image "ghcr.io/acme/api:1.2.3@sha256:${VALID_SHA256_HASH}" --force

echo "[3] Registry port parsing"
run_expect_success \
  "parse registry port image without tag" \
  bash "$GENERATOR_SCRIPT" regportplain "$CHART_ROOT" \
  --image "registry.example.com:5000/team/api" --force

run_expect_success \
  "parse registry port image with tag" \
  bash "$GENERATOR_SCRIPT" regporttag "$CHART_ROOT" \
  --image "registry.example.com:5000/team/api:1.2.0" --force

REGPORT_PLAIN_VALUES="$CHART_ROOT/regportplain/values.yaml"
REGPORT_TAG_VALUES="$CHART_ROOT/regporttag/values.yaml"
assert_file_contains_literal "registry-port plain repository preserved" "$REGPORT_PLAIN_VALUES" "  repository: registry.example.com:5000/team/api"
assert_file_contains_literal "registry-port plain tag remains empty" "$REGPORT_PLAIN_VALUES" "  tag: \"\""
assert_file_contains_literal "registry-port tagged repository auto-split" "$REGPORT_TAG_VALUES" "  repository: registry.example.com:5000/team/api"
assert_file_contains_literal "registry-port tagged value extracted" "$REGPORT_TAG_VALUES" "  tag: \"1.2.0\""

echo "[4] Helm render smoke tests"
run_expect_success \
  "helm lint --strict generated digest chart" \
  helm lint --strict "$CHART_ROOT/digestoksha256"

run_expect_success \
  "helm template generated digest chart" \
  helm template test "$CHART_ROOT/digestoksha256"

echo "[5] Schema guardrails"
SCHEMA_LOG="$TMP_DIR/schema_assertions.log"
set +e
python3 - "$SCHEMA_FILE" >"$SCHEMA_LOG" 2>&1 <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    schema = json.load(fh)

config_map_data = schema["properties"]["configMap"]["properties"]["data"]
secret_string_data = schema["properties"]["secret"]["properties"]["stringData"]

if config_map_data.get("additionalProperties", {}).get("type") != "string":
    raise SystemExit("configMap.data must enforce string values")

if secret_string_data.get("additionalProperties", {}).get("type") != "string":
    raise SystemExit("secret.stringData must enforce string values")
PY
schema_rc=$?
set -e

if [[ $schema_rc -eq 0 ]]; then
  pass "schema constrains ConfigMap/Secret maps to string values"
else
  fail "schema constrains ConfigMap/Secret maps to string values"
  sed 's/^/    /' "$SCHEMA_LOG"
fi

echo ""
echo "Completed with PASS=$PASS FAIL=$FAIL"
if [[ $FAIL -ne 0 ]]; then
  exit 1
fi

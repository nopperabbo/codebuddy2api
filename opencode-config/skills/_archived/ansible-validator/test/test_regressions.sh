#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$SKILL_DIR/scripts"
TEST_DIR="$SKILL_DIR/test"
REAL_PYTHON3="$(command -v python3)"
TMP_ROOT="$(mktemp -d -t ansible-validator-regressions.XXXXXX)"

cleanup() {
    if [ -n "${TMP_ROOT:-}" ] && [ -d "$TMP_ROOT" ]; then
        rm -rf "$TMP_ROOT"
    fi
}
trap cleanup EXIT

strip_ansi() {
    "$REAL_PYTHON3" -c 'import re, sys; sys.stdout.write(re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", sys.stdin.read()))'
}

fail() {
    echo "FAIL: $1" >&2
    exit 1
}

assert_contains() {
    local text="$1"
    local needle="$2"
    local msg="$3"
    if [[ "$text" != *"$needle"* ]]; then
        fail "$msg"
    fi
}

assert_not_contains() {
    local text="$1"
    local needle="$2"
    local msg="$3"
    if [[ "$text" == *"$needle"* ]]; then
        fail "$msg"
    fi
}

test_extract_mixed_import_playbook() {
    local fixture="$TEST_DIR/playbooks/regression-mixed-import.yml"
    local output

    output="$(bash "$SCRIPTS_DIR/extract_ansible_info_wrapper.sh" "$fixture")"

    if ! "$REAL_PYTHON3" -c '
import json
import sys

data = json.load(sys.stdin)
modules = set(data.get("modules", []))

missing = sorted({"shell"} - modules)
forbidden = sorted(modules.intersection({"hosts", "tasks", "import_playbook"}))

if missing or forbidden:
    print(f"missing={missing}; forbidden={forbidden}")
    raise SystemExit(1)
' <<< "$output"
    then
        fail "extract_ansible_info regression: mixed import playbook classification is wrong"
    fi
}

test_check_fqcn_inline_module() {
    local fixture="$TEST_DIR/playbooks/regression-inline-fqcn.yml"
    local output

    output="$(bash "$SCRIPTS_DIR/check_fqcn.sh" "$fixture" | strip_ansi)"

    assert_contains "$output" "[NON-FQCN] shell" \
        "check_fqcn regression: inline short module 'shell: <cmd>' was not detected"
    assert_not_contains "$output" "[NON-FQCN] group" \
        "check_fqcn regression: module argument key 'group:' was falsely detected as module usage"
}

test_inventory_yamllint_unavailable_not_pass() {
    local case_dir="$TMP_ROOT/case-yamllint-missing"
    local bin_dir="$case_dir/bin"
    local inventory_file="$case_dir/hosts.yml"
    local output

    mkdir -p "$bin_dir"
    cat > "$inventory_file" <<'YAML'
all:
  hosts:
    example:
      ansible_host: 127.0.0.1
YAML

    cat > "$bin_dir/python3" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ "\${1:-}" == "-m" && "\${2:-}" == "venv" ]]; then
  venv_dir="\${3:?}"
  mkdir -p "\$venv_dir/bin"
  cat > "\$venv_dir/bin/activate" <<ACT
export PATH="\$venv_dir/bin:\\\$PATH"
ACT
  ln -sf "$REAL_PYTHON3" "\$venv_dir/bin/python3"
  cat > "\$venv_dir/bin/ansible-inventory" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
if [[ "\${1:-}" == "-i" ]]; then
  shift 2
fi
case "\${1:-}" in
  --list)
    cat <<'JSON'
{"_meta":{"hostvars":{"example":{"ansible_host":"127.0.0.1"}}},"all":{"hosts":["example"]}}
JSON
    ;;
  --graph)
    echo "@all:"
    echo "  |--example"
    ;;
  *)
    exit 1
    ;;
esac
STUB
  chmod +x "\$venv_dir/bin/ansible-inventory"
  exit 0
fi
exec "$REAL_PYTHON3" "\$@"
EOF
    chmod +x "$bin_dir/python3"

    cat > "$bin_dir/pip" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$bin_dir/pip"

    output="$(PATH="$bin_dir:/usr/bin:/bin" bash "$SCRIPTS_DIR/validate_inventory.sh" "$inventory_file" | strip_ansi)"

    assert_contains "$output" "YAML syntax check SKIPPED (yamllint unavailable)" \
        "validate_inventory regression: missing yamllint should mark stage as skipped"
    assert_not_contains "$output" "YAML syntax check passed" \
        "validate_inventory regression: missing yamllint must not report YAML PASS"
}

test_inventory_localhost_json_check() {
    local case_dir="$TMP_ROOT/case-localhost-check"
    local bin_dir="$case_dir/bin"
    local inventory_file="$TEST_DIR/inventory/localhost-nested.yml"
    local output

    mkdir -p "$bin_dir"

    cat > "$bin_dir/ansible-inventory" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--version" ]]; then
  echo "ansible-inventory [core 2.18.0]"
  exit 0
fi
if [[ "${1:-}" == "-i" ]]; then
  shift 2
fi
case "${1:-}" in
  --list)
    cat <<'JSON'
{"_meta":{"hostvars":{"localhost":{}}},"all":{"hosts":["localhost"]}}
JSON
    ;;
  --graph)
    echo "@all:"
    echo "  |--localhost"
    ;;
  *)
    exit 1
    ;;
esac
EOF
    chmod +x "$bin_dir/ansible-inventory"

    cat > "$bin_dir/yamllint" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$bin_dir/yamllint"

    output="$(PATH="$bin_dir:/usr/bin:/bin" bash "$SCRIPTS_DIR/validate_inventory.sh" "$inventory_file" | strip_ansi)"

    assert_contains "$output" "'localhost' defined without ansible_connection=local" \
        "validate_inventory regression: localhost warning should come from parsed inventory JSON"
}

test_extract_mixed_import_playbook
test_check_fqcn_inline_module
test_inventory_yamllint_unavailable_not_pass
test_inventory_localhost_json_check

echo "All ansible-validator regression tests passed."

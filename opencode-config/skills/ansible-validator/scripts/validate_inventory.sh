#!/usr/bin/env bash

# Ansible Inventory Validation Script
# Validates inventory files and directories using ansible-inventory
# Automatically installs ansible in a temporary venv if not available

set -e

INVENTORY="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_BLUE='\033[0;34m'
COLOR_RESET='\033[0m'

# Usage check
if [ -z "$INVENTORY" ]; then
    echo "Usage: $0 <inventory-file|inventory-directory>"
    echo ""
    echo "Validates Ansible inventory files and directories."
    echo "Checks syntax, structure, host/group resolution, and variable files."
    echo ""
    echo "Examples:"
    echo "  $0 inventory/hosts.yml"
    echo "  $0 inventory/"
    echo "  $0 production/"
    exit 1
fi

if [ ! -f "$INVENTORY" ] && [ ! -d "$INVENTORY" ]; then
    echo -e "${COLOR_RED}Error: Inventory not found: $INVENTORY${COLOR_RESET}"
    exit 1
fi

# Get absolute path
if [ -f "$INVENTORY" ]; then
    INVENTORY_ABS=$(cd "$(dirname "$INVENTORY")" && pwd)/$(basename "$INVENTORY")
    INVENTORY_DIR=$(dirname "$INVENTORY_ABS")
    SCAN_TYPE="file"
else
    INVENTORY_ABS=$(cd "$INVENTORY" && pwd)
    INVENTORY_DIR="$INVENTORY_ABS"
    SCAN_TYPE="directory"
fi

echo -e "${COLOR_BLUE}========================================${COLOR_RESET}"
echo -e "${COLOR_BLUE}Ansible Inventory Validation${COLOR_RESET}"
echo -e "${COLOR_BLUE}========================================${COLOR_RESET}"
echo ""
echo "Validating: $INVENTORY_ABS"
echo ""

# ─── Tool bootstrap ─────────────────────────────────────────────────────────

TEMP_VENV=""
CLEANUP_VENV=0

run_ansible_inventory() {
    if [ -n "$TEMP_VENV" ]; then
        "$TEMP_VENV/bin/ansible-inventory" "$@"
    else
        ansible-inventory "$@"
    fi
}

resolve_yamllint_bin() {
    if [ -n "$TEMP_VENV" ] && [ -x "$TEMP_VENV/bin/yamllint" ]; then
        echo "$TEMP_VENV/bin/yamllint"
        return 0
    fi
    if command -v yamllint >/dev/null 2>&1; then
        command -v yamllint
        return 0
    fi
    return 1
}

MISSING_TOOLS=()
command -v ansible-inventory >/dev/null 2>&1 || MISSING_TOOLS+=("ansible-inventory")

if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    echo -e "${COLOR_YELLOW}⚠ Missing tools: ${MISSING_TOOLS[*]}${COLOR_RESET}"
    echo ""
    echo "Creating temporary environment..."
    TEMP_VENV=$(mktemp -d -t ansible-inv-validator.XXXXXX)
    CLEANUP_VENV=1

    cleanup() {
        if [ $CLEANUP_VENV -eq 1 ] && [ -n "$TEMP_VENV" ]; then
            echo ""
            echo "Cleaning up temporary environment..."
            rm -rf "$TEMP_VENV"
        fi
    }
    trap cleanup EXIT INT TERM

    echo "Installing ansible + yamllint (this may take a minute)..."
    python3 -m venv "$TEMP_VENV" >/dev/null 2>&1
    source "$TEMP_VENV/bin/activate"
    pip install --quiet --upgrade pip setuptools wheel
    pip install --quiet ansible yamllint
    echo -e "${COLOR_GREEN}✓ Temporary environment ready${COLOR_RESET}"
    echo ""
else
    echo -e "${COLOR_GREEN}✓ ansible-inventory found$(ansible-inventory --version 2>/dev/null | head -1 | awk '{print " - "$0}')${COLOR_RESET}"
    echo ""
fi

ERRORS=0
WARNINGS=0

# ─── Stage 1: YAML syntax check on inventory YAML files ─────────────────────

echo -e "${COLOR_BLUE}[1/4] YAML Syntax Check${COLOR_RESET}"
echo "-----------------------------------"

YAMLLINT_ARGS=()
if [ -f "$SKILL_DIR/assets/.yamllint" ]; then
    YAMLLINT_ARGS=(-c "$SKILL_DIR/assets/.yamllint")
fi

YAMLLINT_BIN="$(resolve_yamllint_bin || true)"

if [ -n "$YAMLLINT_BIN" ]; then
    # Collect YAML files to lint (skip non-inventory files)
    if [ "$SCAN_TYPE" = "file" ]; then
        YAML_FILES=("$INVENTORY_ABS")
    else
        mapfile -t YAML_FILES < <(find "$INVENTORY_ABS" -name "*.yml" -o -name "*.yaml" 2>/dev/null | grep -v ".git/" || true)
    fi

    YAMLLINT_FAILED=0
    for yf in "${YAML_FILES[@]}"; do
        if OUTPUT=$("$YAMLLINT_BIN" "${YAMLLINT_ARGS[@]}" "$yf" 2>&1); then
            if [ -n "$OUTPUT" ]; then
                echo "$OUTPUT"
            fi
            continue
        fi

        if echo "$OUTPUT" | grep -q "error"; then
            echo -e "${COLOR_RED}✗ YAML errors in: $yf${COLOR_RESET}"
            [ -n "$OUTPUT" ] && echo "$OUTPUT"
            YAMLLINT_FAILED=1
        else
            # warnings only
            [ -n "$OUTPUT" ] && echo "$OUTPUT"
        fi
    done

    if [ $YAMLLINT_FAILED -eq 1 ]; then
        echo -e "${COLOR_RED}✗ YAML syntax errors detected${COLOR_RESET}"
        ERRORS=$((ERRORS + 1))
    else
        echo -e "${COLOR_GREEN}✓ YAML syntax check passed${COLOR_RESET}"
    fi
else
    echo -e "${COLOR_YELLOW}⚠ YAML syntax check SKIPPED (yamllint unavailable)${COLOR_RESET}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# ─── Stage 2: Inventory parse and host list ──────────────────────────────────

echo -e "${COLOR_BLUE}[2/4] Inventory Parse (ansible-inventory --list)${COLOR_RESET}"
echo "-----------------------------------"

LIST_STAGE_OK=0
if LIST_OUTPUT=$(run_ansible_inventory -i "$INVENTORY_ABS" --list 2>&1); then
    LIST_STAGE_OK=1
    HOST_COUNT=$(echo "$LIST_OUTPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    hosts = set()
    for k, v in data.items():
        if k == '_meta':
            hosts.update(v.get('hostvars', {}).keys())
        elif isinstance(v, dict):
            hosts.update(v.get('hosts', []))
    print(len(hosts))
except Exception:
    print('?')
" 2>/dev/null || echo "?")
    echo -e "${COLOR_GREEN}✓ Inventory parsed successfully${COLOR_RESET}"
    echo "  Hosts resolved: $HOST_COUNT"
else
    echo -e "${COLOR_RED}✗ Inventory parse failed${COLOR_RESET}"
    echo "$LIST_OUTPUT"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# ─── Stage 3: Group/host graph ───────────────────────────────────────────────

echo -e "${COLOR_BLUE}[3/4] Host Graph (ansible-inventory --graph)${COLOR_RESET}"
echo "-----------------------------------"

if GRAPH_OUTPUT=$(run_ansible_inventory -i "$INVENTORY_ABS" --graph 2>&1); then
    echo -e "${COLOR_GREEN}✓ Host graph resolved${COLOR_RESET}"
    echo ""
    echo "$GRAPH_OUTPUT"
else
    echo -e "${COLOR_RED}✗ Graph resolution failed${COLOR_RESET}"
    echo "$GRAPH_OUTPUT"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# ─── Stage 4: Structure checks ───────────────────────────────────────────────

echo -e "${COLOR_BLUE}[4/4] Structure and Best-Practice Checks${COLOR_RESET}"
echo "-----------------------------------"

STRUCT_WARNINGS=0

# Check for group_vars / host_vars alongside the inventory
check_vars_dir() {
    local label="$1"
    local path="$2"
    if [ -d "$path" ]; then
        FILE_COUNT=$(find "$path" -name "*.yml" -o -name "*.yaml" | wc -l | tr -d ' ')
        echo -e "  ${COLOR_GREEN}✓${COLOR_RESET} $label/ found ($FILE_COUNT var files)"
    fi
}

if [ "$SCAN_TYPE" = "directory" ]; then
    check_vars_dir "group_vars" "$INVENTORY_ABS/group_vars"
    check_vars_dir "host_vars"  "$INVENTORY_ABS/host_vars"
else
    # File-based inventory — check sibling directories
    check_vars_dir "group_vars" "$INVENTORY_DIR/group_vars"
    check_vars_dir "host_vars"  "$INVENTORY_DIR/host_vars"
fi

# Warn if any YAML inventory file contains 'ansible_password' in plaintext
PASSWORD_HITS=0
if [ "$SCAN_TYPE" = "file" ]; then
    PASSWORD_HITS=$(grep -c "ansible_password:" "$INVENTORY_ABS" 2>/dev/null || true)
else
    PASSWORD_HITS=$(grep -r -c "ansible_password:" "$INVENTORY_ABS" 2>/dev/null | awk -F: '{sum+=$2} END{print sum}' || true)
fi

if [ "${PASSWORD_HITS:-0}" -gt 0 ]; then
    echo -e "  ${COLOR_YELLOW}⚠${COLOR_RESET} ansible_password found in plaintext — use ansible-vault or SSH keys"
    STRUCT_WARNINGS=$((STRUCT_WARNINGS + 1))
fi

# Warn if 'localhost' is in the parsed inventory without connection=local.
if [ $LIST_STAGE_OK -eq 1 ]; then
    LOCALHOST_STATUS=$(printf '%s' "$LIST_OUTPUT" | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    print("parse_error")
    raise SystemExit(0)

hosts = set((data.get("_meta") or {}).get("hostvars", {}).keys())
for value in data.values():
    if isinstance(value, dict):
        for host in (value.get("hosts") or []):
            if isinstance(host, str):
                hosts.add(host)

if "localhost" not in hosts:
    print("absent")
    raise SystemExit(0)

hostvars = (data.get("_meta") or {}).get("hostvars", {}) or {}
localhost_vars = hostvars.get("localhost", {}) or {}
connection = localhost_vars.get("ansible_connection", "")
print("ok" if connection == "local" else "warn")
')
    if [ "$LOCALHOST_STATUS" = "warn" ]; then
        echo -e "  ${COLOR_YELLOW}⚠${COLOR_RESET} 'localhost' defined without ansible_connection=local"
        STRUCT_WARNINGS=$((STRUCT_WARNINGS + 1))
    elif [ "$LOCALHOST_STATUS" = "parse_error" ]; then
        echo -e "  ${COLOR_YELLOW}⚠${COLOR_RESET} Unable to evaluate localhost connection from inventory JSON"
        STRUCT_WARNINGS=$((STRUCT_WARNINGS + 1))
    fi
fi

if [ $STRUCT_WARNINGS -eq 0 ]; then
    echo -e "  ${COLOR_GREEN}✓${COLOR_RESET} No structural issues found"
fi

WARNINGS=$((WARNINGS + STRUCT_WARNINGS))
echo ""

# ─── Summary ─────────────────────────────────────────────────────────────────

echo -e "${COLOR_BLUE}========================================${COLOR_RESET}"
echo -e "${COLOR_BLUE}Inventory Validation Summary${COLOR_RESET}"
echo -e "${COLOR_BLUE}========================================${COLOR_RESET}"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${COLOR_GREEN}✓ Inventory is valid — no issues detected!${COLOR_RESET}"
    if [ -n "$TEMP_VENV" ]; then
        echo ""
        echo "Note: ansible was installed in a temporary environment."
        echo "To install permanently: pip3 install ansible"
    fi
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${COLOR_YELLOW}⚠ Inventory validation completed with $WARNINGS warning(s)${COLOR_RESET}"
    echo ""
    echo "Review warnings above and consider:"
    echo "  - Using Ansible Vault for any plaintext credentials"
    echo "  - Defining ansible_connection=local for localhost entries"
    echo "  - Consulting references/best_practices.md for inventory organisation"
    if [ -n "$TEMP_VENV" ]; then
        echo ""
        echo "Note: ansible was installed in a temporary environment."
        echo "To install permanently: pip3 install ansible"
    fi
    exit 0
else
    echo -e "${COLOR_RED}✗ Inventory validation failed with $ERRORS error(s) and $WARNINGS warning(s)${COLOR_RESET}"
    echo ""
    echo "Remediation steps:"
    echo "  1. Fix YAML syntax errors reported above"
    echo "  2. Ensure host/group names follow Ansible naming rules"
    echo "  3. Verify all referenced groups and hosts are defined"
    echo "  4. Consult references/common_errors.md for inventory error solutions"
    exit 1
fi

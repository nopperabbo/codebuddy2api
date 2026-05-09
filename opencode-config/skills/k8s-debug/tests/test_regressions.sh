#!/usr/bin/env bash
#
# Regression tests for k8s-debug shell scripts.
# Validates:
# - network_debug.sh secure/insecure API probing and exit codes
# - cluster_health.sh blocked/check-failure exit codes
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly SKILL_DIR

NETWORK_SCRIPT="$SKILL_DIR/scripts/network_debug.sh"
CLUSTER_SCRIPT="$SKILL_DIR/scripts/cluster_health.sh"
readonly NETWORK_SCRIPT
readonly CLUSTER_SCRIPT

TMP_DIR="$(mktemp -d)"
KUBECTL_LOG="$TMP_DIR/kubectl.log"
readonly TMP_DIR
readonly KUBECTL_LOG

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

PASS=0
FAIL=0
OUTPUT=""
EXIT_CODE=0

pass() {
    echo "  PASS: $1"
    PASS=$((PASS + 1))
}

fail() {
    echo "  FAIL: $1"
    FAIL=$((FAIL + 1))
}

reset_stub_env() {
    unset K8S_STUB_CONTEXT_FAIL || true
    unset K8S_STUB_CAN_I_EXEC || true
    unset K8S_STUB_SA_FILES || true
    unset K8S_STUB_EXPECT_SECURE || true
    unset K8S_STUB_EXPECT_INSECURE || true
    unset K8S_STUB_DNS_FAIL || true
    unset K8S_STUB_FAIL_NODE_LIST || true
}

create_kubectl_stub() {
    mkdir -p "$TMP_DIR/bin"

    cat > "$TMP_DIR/bin/kubectl" <<'EOF'
#!/usr/bin/env bash
set -u

LOG_FILE="${KUBECTL_STUB_LOG:-/dev/null}"
printf '%s\n' "$*" >> "$LOG_FILE"

args=("$@")
if [[ "${args[0]:-}" == --request-timeout=* ]]; then
    args=("${args[@]:1}")
fi

if [[ "${#args[@]}" -eq 0 ]]; then
    exit 0
fi

joined=" ${args[*]} "
cmd="${args[0]}"
sub="${args[1]:-}"

if [[ "$cmd" == "config" && "$sub" == "current-context" ]]; then
    if [[ "${K8S_STUB_CONTEXT_FAIL:-0}" == "1" ]]; then
        echo "no context" >&2
        exit 1
    fi
    echo "stub-context"
    exit 0
fi

if [[ "$cmd" == "auth" && "$sub" == "can-i" ]]; then
    if [[ "$joined" == *" create pods/exec "* ]]; then
        echo "${K8S_STUB_CAN_I_EXEC:-yes}"
    else
        echo "yes"
    fi
    exit 0
fi

if [[ "$cmd" == "cluster-info" ]]; then
    echo "Kubernetes control plane is running"
    exit 0
fi

if [[ "$cmd" == "version" ]]; then
    echo "Client Version: v1.30.0"
    exit 0
fi

if [[ "$cmd" == "top" ]]; then
    echo "stub metrics"
    exit 0
fi

if [[ "$cmd" == "logs" ]]; then
    echo "stub logs"
    exit 0
fi

if [[ "$cmd" == "describe" && "$sub" == "pod" ]]; then
    echo "IP: 10.0.0.10"
    echo "Controlled By: ReplicaSet/demo"
    exit 0
fi

if [[ "$cmd" == "get" ]]; then
    resource="${args[1]:-}"

    if [[ "$resource" == "--raw=/readyz?verbose" || "$resource" == "--raw=/healthz?verbose" ]]; then
        echo "ok"
        exit 0
    fi

    if [[ "$resource" == "componentstatuses" ]]; then
        echo "scheduler Healthy"
        exit 0
    fi

    if [[ "$resource" == "namespace" ]]; then
        if [[ "${K8S_STUB_CONTEXT_FAIL:-0}" == "1" ]]; then
            exit 1
        fi
        echo "namespace/${args[2]:-default}"
        exit 0
    fi

    if [[ "$resource" == "pod" ]]; then
        if [[ "$joined" == *"jsonpath={.status.podIP}"* ]]; then
            echo "10.0.0.10"
            exit 0
        fi
        if [[ "$joined" == *"jsonpath={.status.hostIP}"* ]]; then
            echo "192.168.1.10"
            exit 0
        fi
        if [[ "$joined" == *"--show-labels"* ]]; then
            echo "demo-pod app=demo"
            exit 0
        fi
        if [[ "$joined" == *"-o wide"* ]]; then
            echo "demo-pod 1/1 Running 0"
            exit 0
        fi
        echo "pod/${args[2]:-demo-pod}"
        exit 0
    fi

    if [[ "$resource" == "nodes" ]]; then
        if [[ "$joined" == *" -o wide "* && "${K8S_STUB_FAIL_NODE_LIST:-0}" == "1" ]]; then
            echo "node list failed" >&2
            exit 1
        fi
        if [[ "$joined" == *"jsonpath="* ]]; then
            echo -e "node-a\tTrue"
            exit 0
        fi
        echo "node-a Ready"
        exit 0
    fi

    if [[ "$resource" == "events" ]]; then
        echo "Normal Started pod/demo-pod"
        exit 0
    fi

    echo "stub get $resource"
    exit 0
fi

if [[ "$cmd" == "exec" ]]; then
    idx=-1
    for i in "${!args[@]}"; do
        if [[ "${args[$i]}" == "--" ]]; then
            idx=$i
            break
        fi
    done

    if (( idx < 0 )); then
        echo "malformed exec command" >&2
        exit 1
    fi

    exec_args=("${args[@]:idx+1}")
    first="${exec_args[0]:-}"

    if [[ "$first" == "test" && "${exec_args[1]:-}" == "-r" ]]; then
        if [[ "${K8S_STUB_SA_FILES:-present}" == "present" ]]; then
            exit 0
        fi
        exit 1
    fi

    if [[ "$first" == "cat" && "${exec_args[1]:-}" == "/var/run/secrets/kubernetes.io/serviceaccount/token" ]]; then
        if [[ "${K8S_STUB_SA_FILES:-present}" == "present" ]]; then
            echo "stub-token"
            exit 0
        fi
        exit 1
    fi

    if [[ "$first" == "cat" && "${exec_args[1]:-}" == "/etc/resolv.conf" ]]; then
        echo "nameserver 10.96.0.10"
        exit 0
    fi

    if [[ "$first" == "nslookup" ]]; then
        if [[ "${K8S_STUB_DNS_FAIL:-0}" == "1" ]]; then
            exit 1
        fi
        echo "Name: kubernetes.default.svc.cluster.local"
        exit 0
    fi

    if [[ "$first" == "getent" ]]; then
        if [[ "${K8S_STUB_DNS_FAIL:-0}" == "1" ]]; then
            exit 1
        fi
        echo "10.96.0.1 kubernetes.default.svc.cluster.local"
        exit 0
    fi

    if [[ "$first" == "curl" ]]; then
        has_cacert=0
        has_insecure=0
        for arg in "${exec_args[@]}"; do
            [[ "$arg" == "--cacert" ]] && has_cacert=1
            [[ "$arg" == "-k" ]] && has_insecure=1
        done

        if [[ "${K8S_STUB_EXPECT_SECURE:-0}" == "1" ]]; then
            [[ "$has_cacert" -eq 1 && "$has_insecure" -eq 0 ]] || exit 1
        fi
        if [[ "${K8S_STUB_EXPECT_INSECURE:-0}" == "1" ]]; then
            [[ "$has_insecure" -eq 1 ]] || exit 1
        fi
        exit 0
    fi

    if [[ "$first" == "wget" ]]; then
        has_ca=0
        has_no_check=0
        for arg in "${exec_args[@]}"; do
            [[ "$arg" == --ca-certificate=* ]] && has_ca=1
            [[ "$arg" == "--no-check-certificate" ]] && has_no_check=1
        done

        if [[ "${K8S_STUB_EXPECT_SECURE:-0}" == "1" ]]; then
            [[ "$has_ca" -eq 1 ]] || exit 1
        fi
        if [[ "${K8S_STUB_EXPECT_INSECURE:-0}" == "1" ]]; then
            [[ "$has_no_check" -eq 1 ]] || exit 1
        fi
        exit 0
    fi

    exit 0
fi

echo "stub kubectl default response"
exit 0
EOF

    chmod +x "$TMP_DIR/bin/kubectl"
}

run_script() {
    local script="$1"
    shift

    OUTPUT=""
    EXIT_CODE=0
    : > "$KUBECTL_LOG"
    OUTPUT=$(
        PATH="$TMP_DIR/bin:/usr/bin:/bin:$PATH" \
        KUBECTL_STUB_LOG="$KUBECTL_LOG" \
        bash "$script" "$@" 2>&1
    ) || EXIT_CODE=$?
}

assert_exit() {
    local label="$1"
    local expected="$2"
    if [[ "$EXIT_CODE" -eq "$expected" ]]; then
        pass "$label"
    else
        fail "$label (expected exit $expected, got $EXIT_CODE)"
        echo "$OUTPUT" | sed 's/^/    /'
    fi
}

assert_output_contains() {
    local label="$1"
    local pattern="$2"
    if echo "$OUTPUT" | grep -qE -- "$pattern"; then
        pass "$label"
    else
        fail "$label (pattern not found: $pattern)"
        echo "$OUTPUT" | sed 's/^/    /'
    fi
}

assert_log_contains() {
    local label="$1"
    local pattern="$2"
    if grep -qE -- "$pattern" "$KUBECTL_LOG"; then
        pass "$label"
    else
        fail "$label (pattern not found in kubectl log: $pattern)"
        sed 's/^/    /' "$KUBECTL_LOG"
    fi
}

assert_log_not_contains() {
    local label="$1"
    local pattern="$2"
    if grep -qE -- "$pattern" "$KUBECTL_LOG"; then
        fail "$label (unexpected pattern found in kubectl log: $pattern)"
        sed 's/^/    /' "$KUBECTL_LOG"
    else
        pass "$label"
    fi
}

assert_no_bytecode_artifacts() {
    local findings
    findings="$(find "$SKILL_DIR" -type f \( -name '*.pyc' -o -path '*/__pycache__/*' \) -print)"
    if [[ -z "$findings" ]]; then
        pass "no Python bytecode artifacts exist under k8s-debug"
    else
        fail "no Python bytecode artifacts exist under k8s-debug"
        echo "$findings" | sed 's/^/    /'
    fi
}

echo "Running k8s-debug shell regressions..."
create_kubectl_stub

echo ""
echo "[P1] bytecode artifact hygiene"
assert_no_bytecode_artifacts

echo ""
echo "[P0] network_debug secure-by-default API probe"
reset_stub_env
export K8S_STUB_EXPECT_SECURE=1
run_script "$NETWORK_SCRIPT" demo-pod
assert_exit "secure default run returns success" 0
assert_log_contains "secure probe passes --cacert" "--cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
assert_log_not_contains "secure probe does not use -k" " exec .* -- curl .* -k "

echo ""
echo "[P0] network_debug insecure mode remains explicit"
reset_stub_env
export K8S_STUB_EXPECT_INSECURE=1
export K8S_STUB_SA_FILES=missing
run_script "$NETWORK_SCRIPT" --insecure demo-pod
assert_exit "insecure override run returns success" 0
assert_output_contains "prints insecure override warning" "Insecure TLS mode enabled"
assert_log_contains "insecure probe uses -k" " exec .* -- curl .* -k "

echo ""
echo "[P0/P1] secure mode fails when SA CA/token are missing"
reset_stub_env
export K8S_STUB_SA_FILES=missing
run_script "$NETWORK_SCRIPT" demo-pod
assert_exit "missing SA materials produce partial-failure exit code" 1
assert_output_contains "missing SA files are reported" "service account CA/token files are missing in the pod"

echo ""
echo "[P1] --strict upgrades warnings in network_debug"
reset_stub_env
export K8S_STUB_CAN_I_EXEC=no
run_script "$NETWORK_SCRIPT" --strict demo-pod
assert_exit "strict mode returns failure on warnings" 1
assert_output_contains "RBAC warning is surfaced" "RBAC may block 'kubectl exec'; in-pod checks may fail"

echo ""
echo "[P1] cluster_health blocked precondition returns exit 2"
reset_stub_env
export K8S_STUB_CONTEXT_FAIL=1
run_script "$CLUSTER_SCRIPT"
assert_exit "missing context is blocked" 2
assert_output_contains "blocked error message is clear" "No active Kubernetes context"

echo ""
echo "[P1] cluster_health check failure returns exit 1"
reset_stub_env
export K8S_STUB_FAIL_NODE_LIST=1
run_script "$CLUSTER_SCRIPT"
assert_exit "node list failure maps to exit 1" 1
assert_output_contains "node list failure is reported" "Node list failed; continuing"

echo ""
echo "Test summary: PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -ne 0 ]]; then
    exit 1
fi

echo "All k8s-debug shell regressions passed."

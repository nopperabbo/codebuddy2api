#!/usr/bin/env bash
# Kubernetes Network Debugging Script
# Diagnoses pod/service connectivity with graceful fallbacks.

set -uo pipefail

REQUEST_TIMEOUT="${K8S_REQUEST_TIMEOUT:-15s}"
NAMESPACE="default"
POD_NAME=""
STRICT_MODE=0
INSECURE_TLS=0

WARN_COUNT=0
CHECK_FAIL_COUNT=0
BLOCKED_COUNT=0

SERVICEACCOUNT_DIR="/var/run/secrets/kubernetes.io/serviceaccount"
SERVICEACCOUNT_CA="${SERVICEACCOUNT_DIR}/ca.crt"
SERVICEACCOUNT_TOKEN_FILE="${SERVICEACCOUNT_DIR}/token"
KUBERNETES_API_URL="https://kubernetes.default.svc/api"

usage() {
    echo "Usage: $0 [--strict] [--insecure] [namespace] <pod-name>"
    echo "Examples:"
    echo "  $0 my-pod"
    echo "  $0 default my-pod"
    echo "  $0 --insecure default my-pod"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --strict)
            STRICT_MODE=1
            shift
            ;;
        --insecure)
            INSECURE_TLS=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "ERROR: Unknown option '$1'." >&2
            usage
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

case "$#" in
    1)
        POD_NAME="$1"
        ;;
    2)
        NAMESPACE="$1"
        POD_NAME="$2"
        ;;
    *)
        usage
        exit 1
        ;;
esac

timestamp_utc() {
    date -u +"%Y-%m-%d %H:%M:%S UTC"
}

section() {
    printf "\n## %s ##\n" "$1"
}

warn_raw() {
    printf "WARN: %s\n" "$1" >&2
}

warn() {
    warn_raw "$1"
    WARN_COUNT=$((WARN_COUNT + 1))
}

info() {
    printf "INFO: %s\n" "$1"
}

have_cmd() {
    command -v "$1" >/dev/null 2>&1
}

kubectl_cmd() {
    kubectl --request-timeout="$REQUEST_TIMEOUT" "$@"
}

can_i() {
    local result
    result="$(kubectl_cmd auth can-i "$@" 2>/dev/null || true)"
    [ "$result" = "yes" ]
}

record_check_failure() {
    local message="$1"
    warn_raw "$message"
    CHECK_FAIL_COUNT=$((CHECK_FAIL_COUNT + 1))
}

run_or_warn() {
    local description="$1"
    shift
    if ! "$@"; then
        record_check_failure "${description} failed; continuing."
        return 1
    fi
    return 0
}

run_pipe_or_warn() {
    local description="$1"
    local cmd="$2"
    if ! bash -o pipefail -c "$cmd"; then
        record_check_failure "${description} failed; continuing."
        return 1
    fi
    return 0
}

pod_exec() {
    kubectl_cmd exec "$POD_NAME" -n "$NAMESPACE" -- "$@"
}

blocked_exit() {
    local message="$1"
    BLOCKED_COUNT=$((BLOCKED_COUNT + 1))
    printf "ERROR: %s\n" "$message" >&2
    exit 2
}

read_serviceaccount_token() {
    local token
    token="$(pod_exec cat "$SERVICEACCOUNT_TOKEN_FILE" 2>/dev/null || true)"
    token="${token//$'\r'/}"
    token="${token//$'\n'/}"
    printf "%s" "$token"
}

api_probe_secure() {
    local token

    if ! pod_exec test -r "$SERVICEACCOUNT_CA" >/dev/null 2>&1 || \
        ! pod_exec test -r "$SERVICEACCOUNT_TOKEN_FILE" >/dev/null 2>&1; then
        echo "service account CA/token files are missing in the pod. Use --insecure only for explicit troubleshooting override." >&2
        return 1
    fi

    token="$(read_serviceaccount_token)"
    if [ -z "$token" ]; then
        echo "service account token is empty; cannot authenticate secure API probe." >&2
        return 1
    fi

    if pod_exec curl --fail --silent --show-error --cacert "$SERVICEACCOUNT_CA" --max-time 5 \
        -H "Authorization: Bearer $token" "$KUBERNETES_API_URL" >/dev/null 2>&1; then
        return 0
    fi

    if pod_exec wget -q --timeout=5 --ca-certificate="$SERVICEACCOUNT_CA" \
        --header="Authorization: Bearer $token" -O /dev/null "$KUBERNETES_API_URL" >/dev/null 2>&1; then
        return 0
    fi

    echo "curl/wget secure API probe failed in the container (missing tools, auth failure, or blocked egress)." >&2
    return 1
}

api_probe_insecure() {
    local token
    token="$(read_serviceaccount_token)"
    warn "Insecure TLS mode enabled (--insecure). Certificate validation is bypassed for API probe."

    if [ -n "$token" ]; then
        if pod_exec curl --fail --silent --show-error -k --max-time 5 \
            -H "Authorization: Bearer $token" "$KUBERNETES_API_URL" >/dev/null 2>&1; then
            return 0
        fi
        if pod_exec wget -q --timeout=5 --no-check-certificate \
            --header="Authorization: Bearer $token" -O /dev/null "$KUBERNETES_API_URL" >/dev/null 2>&1; then
            return 0
        fi
    else
        if pod_exec curl --fail --silent --show-error -k --max-time 5 \
            "$KUBERNETES_API_URL" >/dev/null 2>&1; then
            return 0
        fi
        if pod_exec wget -q --timeout=5 --no-check-certificate \
            -O /dev/null "$KUBERNETES_API_URL" >/dev/null 2>&1; then
            return 0
        fi
    fi

    echo "curl/wget insecure API probe failed in the container (missing tools, auth failure, or blocked egress)." >&2
    return 1
}

api_probe() {
    if [ "$INSECURE_TLS" -eq 1 ]; then
        api_probe_insecure
        return $?
    fi
    api_probe_secure
}

finalize_exit() {
    if [ "$BLOCKED_COUNT" -gt 0 ]; then
        return 2
    fi
    if [ "$CHECK_FAIL_COUNT" -gt 0 ]; then
        return 1
    fi
    if [ "$STRICT_MODE" -eq 1 ] && [ "$WARN_COUNT" -gt 0 ]; then
        return 1
    fi
    return 0
}

if ! have_cmd kubectl; then
    blocked_exit "kubectl is not installed or not in PATH."
fi

if ! kubectl_cmd config current-context >/dev/null 2>&1; then
    blocked_exit "No active Kubernetes context. Run 'kubectl config current-context' to troubleshoot."
fi

if ! kubectl_cmd get namespace "$NAMESPACE" >/dev/null 2>&1; then
    blocked_exit "Namespace '$NAMESPACE' was not found or is not accessible."
fi

if ! kubectl_cmd get pod "$POD_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    blocked_exit "Pod '$POD_NAME' in namespace '$NAMESPACE' was not found or is not accessible."
fi

echo "========================================"
echo "Network Debugging for Pod: $POD_NAME"
echo "Namespace: $NAMESPACE"
echo "Timestamp: $(timestamp_utc)"
echo "========================================"

section "PREFLIGHT"
run_or_warn "Current context check" kubectl_cmd config current-context
if ! can_i get pods -n "$NAMESPACE"; then
    warn "RBAC may block pod metadata reads in namespace '$NAMESPACE'."
fi
if ! can_i create pods/exec -n "$NAMESPACE"; then
    warn "RBAC may block 'kubectl exec'; in-pod checks may fail."
fi

section "POD NETWORK INFORMATION"
POD_IP="$(kubectl_cmd get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.status.podIP}' 2>/dev/null || true)"
HOST_IP="$(kubectl_cmd get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.status.hostIP}' 2>/dev/null || true)"
echo "Pod IP: ${POD_IP:-Unavailable}"
echo "Host IP: ${HOST_IP:-Unavailable}"
run_or_warn "Pod wide status query" kubectl_cmd get pod "$POD_NAME" -n "$NAMESPACE" -o wide

section "DNS CONFIGURATION"
run_or_warn "Pod DNS config read" pod_exec cat /etc/resolv.conf

section "DNS RESOLUTION TEST"
echo "Testing kubernetes.default.svc.cluster.local:"
if pod_exec nslookup kubernetes.default.svc.cluster.local 2>/dev/null; then
    :
elif pod_exec getent hosts kubernetes.default.svc.cluster.local 2>/dev/null; then
    :
else
    record_check_failure "DNS lookup test failed (utilities unavailable or DNS lookup failed)."
fi

section "NETWORK CONNECTIVITY TESTS"
echo "Testing connection to kubernetes.default.svc:"
run_or_warn "Kubernetes API connectivity test from pod" api_probe

section "SERVICES IN NAMESPACE"
run_or_warn "Service list query" kubectl_cmd get svc -n "$NAMESPACE"

section "ENDPOINTS"
run_or_warn "Endpoint list query" kubectl_cmd get endpoints -n "$NAMESPACE"

section "NETWORK POLICIES"
run_or_warn "Network policy list query" kubectl_cmd get networkpolicies -n "$NAMESPACE"

section "POD NETWORK DETAILS"
run_pipe_or_warn "Pod describe network details query" "kubectl --request-timeout=\"$REQUEST_TIMEOUT\" describe pod \"$POD_NAME\" -n \"$NAMESPACE\" | grep -A 20 '^IP:'"

section "POD LABELS (FOR NETWORKPOLICY MATCHING)"
run_or_warn "Pod label query" kubectl_cmd get pod "$POD_NAME" -n "$NAMESPACE" --show-labels

section "IPTABLES RULES (IF ACCESSIBLE)"
if ! pod_exec iptables -L -n 2>/dev/null; then
    info "iptables output not available (requires privileged container/tools)."
fi

section "NETWORK INTERFACES"
if pod_exec ip addr 2>/dev/null; then
    :
elif pod_exec ifconfig 2>/dev/null; then
    :
else
    info "Network interface tools are not available in this container."
fi

section "ROUTING TABLE"
if pod_exec ip route 2>/dev/null; then
    :
elif pod_exec route 2>/dev/null; then
    :
else
    info "Routing table tools are not available in this container."
fi

section "COREDNS LOGS (LAST 20 LINES)"
if kubectl_cmd logs -n kube-system -l k8s-app=kube-dns --tail=20 2>/dev/null; then
    :
elif kubectl_cmd logs -n kube-system -l k8s-app=coredns --tail=20 2>/dev/null; then
    :
else
    warn "CoreDNS logs are not accessible."
fi

echo -e "\n========================================"
echo "Network debugging completed at $(timestamp_utc)"
echo "Warnings: $WARN_COUNT | Check failures: $CHECK_FAIL_COUNT | Blocked checks: $BLOCKED_COUNT"
echo "========================================"

finalize_exit
exit $?

#!/usr/bin/env bash
# Generate a production-ready Python Dockerfile with multi-stage build

set -euo pipefail

# Default values
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
PORT="${PORT:-8000}"
OUTPUT_FILE="${OUTPUT_FILE:-Dockerfile}"
LEGACY_ENTRY="${APP_ENTRY:-app.py}"
LEGACY_ENTRY_SET="false"
ENTRY_CMD="${ENTRY_CMD:-}"
ENTRY_ARGS=()

# Usage
usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Generate a production-ready Python Dockerfile with multi-stage build.

OPTIONS:
    -v, --version VERSION     Python version (default: 3.12)
    -p, --port PORT          Port to expose (default: 8000)
    -o, --output FILE        Output file (default: Dockerfile)
    -e, --entry COMMAND      Legacy entry syntax (simple whitespace split only)
        --entry-cmd COMMAND  Preferred command binary/executable
        --entry-arg ARG      Preferred command argument (repeatable; preserves spaces)
    -h, --help               Show this help message

EXAMPLES:
    # Basic Python app
    $0

    # FastAPI app
    $0 --version 3.12 --port 8000

    # Django app
    $0 --port 8080 --entry "python manage.py runserver 0.0.0.0:8080"

    # Preferred structured entrypoint (preserves quoted args exactly)
    $0 --entry-cmd python --entry-arg -m --entry-arg uvicorn --entry-arg main:app --entry-arg --log-config --entry-arg "configs/logging prod.yaml"

EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            PYTHON_VERSION="$2"
            shift 2
            ;;
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -e|--entry)
            LEGACY_ENTRY="$2"
            LEGACY_ENTRY_SET="true"
            shift 2
            ;;
        --entry-cmd)
            ENTRY_CMD="$2"
            shift 2
            ;;
        --entry-arg)
            ENTRY_ARGS+=("$2")
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Escape values that are inserted into JSON-form CMD arrays.
escape_json_string() {
    local input="$1"
    input="${input//\\/\\\\}"
    input="${input//\"/\\\"}"
    printf '%s' "$input"
}

# Escape values that are inserted into sed replacement strings.
escape_sed_replacement() {
    local input="$1"
    input="${input//\\/\\\\}"
    input="${input//&/\\&}"
    input="${input//|/\\|}"
    printf '%s' "$input"
}

# Validate mutually exclusive entrypoint interfaces.
if [[ -n "$ENTRY_CMD" && "$LEGACY_ENTRY_SET" == "true" ]]; then
    echo "ERROR: use either --entry or --entry-cmd/--entry-arg, not both." >&2
    exit 1
fi

if [[ -z "$ENTRY_CMD" && ${#ENTRY_ARGS[@]} -gt 0 ]]; then
    echo "ERROR: --entry-arg requires --entry-cmd." >&2
    exit 1
fi

# Build CMD instruction.
# Preferred mode:
#   --entry-cmd <cmd> --entry-arg <arg> --entry-arg <arg>
# Legacy mode:
#   --entry "<simple whitespace-delimited command>"
# Quoted legacy entries are rejected because they cannot be parsed safely.
if [[ -n "$ENTRY_CMD" ]]; then
    CMD_PARTS=("$ENTRY_CMD" "${ENTRY_ARGS[@]}")
else
    if [[ "$LEGACY_ENTRY" == *"\""* || "$LEGACY_ENTRY" == *"'"* ]]; then
        echo "ERROR: quoted --entry values are not supported. Use --entry-cmd/--entry-arg." >&2
        exit 1
    fi

    if [[ "$LEGACY_ENTRY" =~ [[:space:]] ]]; then
        read -r -a CMD_PARTS <<< "$LEGACY_ENTRY"
    else
        CMD_PARTS=("python" "$LEGACY_ENTRY")
    fi
fi

if [[ -z "${CMD_PARTS[0]:-}" ]]; then
    echo "ERROR: entry command cannot be empty." >&2
    exit 1
fi

_json_parts=()
for _token in "${CMD_PARTS[@]}"; do
    _json_parts+=("\"$(escape_json_string "$_token")\"")
done
CMD_INSTRUCTION="CMD [$(IFS=', '; echo "${_json_parts[*]}")]"
CMD_INSTRUCTION_SED="$(escape_sed_replacement "$CMD_INSTRUCTION")"

# Generate Dockerfile
cat > "$OUTPUT_FILE" <<'EOF'
# syntax=docker/dockerfile:1

# Build stage
FROM python:PYTHON_VERSION-slim AS builder
WORKDIR /app

# Install build dependencies
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:PYTHON_VERSION-slim AS production
WORKDIR /app

# Create non-root user
RUN useradd -m -u 1001 appuser

# Copy dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# Update PATH and set Python production env vars
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Expose port
EXPOSE PORT_NUMBER

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:PORT_NUMBER/health').read()" || exit 1

# Start application
CMD_INSTRUCTION_PLACEHOLDER
EOF

# Replace placeholders
sed -i.bak "s/PYTHON_VERSION/$PYTHON_VERSION/g" "$OUTPUT_FILE"
sed -i.bak "s/PORT_NUMBER/$PORT/g" "$OUTPUT_FILE"
sed -i.bak "s|CMD_INSTRUCTION_PLACEHOLDER|$CMD_INSTRUCTION_SED|g" "$OUTPUT_FILE"

# Clean up backup files
rm -f "${OUTPUT_FILE}.bak"

echo "✓ Generated Python Dockerfile: $OUTPUT_FILE"
echo "  Python version: $PYTHON_VERSION"
echo "  Port: $PORT"
if [[ -n "$ENTRY_CMD" ]]; then
    ENTRY_DISPLAY="$ENTRY_CMD"
    for _arg in "${ENTRY_ARGS[@]}"; do
        ENTRY_DISPLAY+=" $(printf '%q' "$_arg")"
    done
else
    ENTRY_DISPLAY="$LEGACY_ENTRY"
fi
echo "  Entry point: $ENTRY_DISPLAY"

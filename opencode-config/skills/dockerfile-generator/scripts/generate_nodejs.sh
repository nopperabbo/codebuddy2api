#!/usr/bin/env bash
# Generate a production-ready Node.js Dockerfile with multi-stage build

set -euo pipefail

# Default values
NODE_VERSION="${NODE_VERSION:-20}"
PORT="${PORT:-3000}"
OUTPUT_FILE="${OUTPUT_FILE:-Dockerfile}"
LEGACY_ENTRY="${APP_ENTRY:-index.js}"
LEGACY_ENTRY_SET="false"
ENTRY_CMD="${ENTRY_CMD:-}"
ENTRY_ARGS=()
BUILD_STAGE="${BUILD_STAGE:-false}"

# Usage
usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Generate a production-ready Node.js Dockerfile with multi-stage build.

OPTIONS:
    -v, --version VERSION     Node.js version (default: 20)
    -p, --port PORT          Port to expose (default: 3000)
    -o, --output FILE        Output file (default: Dockerfile)
    -e, --entry COMMAND      Legacy entry syntax (simple whitespace split only)
        --entry-cmd COMMAND  Preferred command binary/executable
        --entry-arg ARG      Preferred command argument (repeatable; preserves spaces)
    -b, --build              Include build stage for compilation (installs all deps, runs npm run build, prunes dev deps)
    -h, --help               Show this help message

EXAMPLES:
    # Basic Node.js app
    $0

    # Next.js app with build stage
    $0 --version 20 --port 3000 --build --entry "npm start"

    # Preferred structured entrypoint (preserves quoted args exactly)
    $0 --entry-cmd node --entry-arg server.js --entry-arg --message --entry-arg "hello world"

    # Custom port and legacy entry point
    $0 --port 8080 --entry "server.js"

EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            NODE_VERSION="$2"
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
        -b|--build)
            BUILD_STAGE="true"
            shift
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
        CMD_PARTS=("node" "$LEGACY_ENTRY")
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

# Generate Dockerfile — two templates to avoid complex sed escaping around &&.
# The build template installs ALL deps (including dev) so that build tools like
# tsc, vite, webpack etc. are available, then prunes dev deps after the build so
# the production stage receives a clean node_modules.
if [ "$BUILD_STAGE" = "true" ]; then
    cat > "$OUTPUT_FILE" <<'EOF'
# syntax=docker/dockerfile:1

# Build stage — install all deps (including devDependencies) required by the
# build step, compile the application, then prune to production-only deps.
FROM node:NODE_VERSION-alpine AS builder
WORKDIR /app

# Copy dependency files for caching
COPY package*.json ./

# Install all dependencies (including devDependencies needed for build)
RUN npm ci && \
    npm cache clean --force

# Copy application code
COPY . .

# Build application and prune dev dependencies so the production stage
# receives only what is needed at runtime.
RUN npm run build && \
    npm prune --omit=dev

# Production stage
FROM node:NODE_VERSION-alpine AS production
WORKDIR /app

# Set production environment
ENV NODE_ENV=production

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# Copy pruned node_modules and built application from builder
COPY --from=builder --chown=nodejs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nodejs:nodejs /app .

# Switch to non-root user
USER nodejs

# Expose port
EXPOSE PORT_NUMBER

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:PORT_NUMBER/health', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})" || exit 1

# Start application
CMD_INSTRUCTION_PLACEHOLDER
EOF
else
    cat > "$OUTPUT_FILE" <<'EOF'
# syntax=docker/dockerfile:1

# Build stage
FROM node:NODE_VERSION-alpine AS builder
WORKDIR /app

# Copy dependency files for caching
COPY package*.json ./

# Install production dependencies only
RUN npm ci --omit=dev && \
    npm cache clean --force

# Copy application code
COPY . .

# Production stage
FROM node:NODE_VERSION-alpine AS production
WORKDIR /app

# Set production environment
ENV NODE_ENV=production

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# Copy dependencies from builder
COPY --from=builder --chown=nodejs:nodejs /app/node_modules ./node_modules

# Copy application from builder
COPY --chown=nodejs:nodejs . .

# Switch to non-root user
USER nodejs

# Expose port
EXPOSE PORT_NUMBER

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:PORT_NUMBER/health', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})" || exit 1

# Start application
CMD_INSTRUCTION_PLACEHOLDER
EOF
fi

# Replace placeholders
sed -i.bak "s/NODE_VERSION/$NODE_VERSION/g" "$OUTPUT_FILE"
sed -i.bak "s/PORT_NUMBER/$PORT/g" "$OUTPUT_FILE"
sed -i.bak "s|CMD_INSTRUCTION_PLACEHOLDER|$CMD_INSTRUCTION_SED|g" "$OUTPUT_FILE"

# Clean up backup files
rm -f "${OUTPUT_FILE}.bak"

echo "✓ Generated Node.js Dockerfile: $OUTPUT_FILE"
echo "  Node version: $NODE_VERSION"
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
echo "  Build stage: $BUILD_STAGE"

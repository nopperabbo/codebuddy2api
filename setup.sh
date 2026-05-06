#!/bin/bash
# ============================================================
# CodeBuddy2API + OpenCode Config - One-Click Setup
# ============================================================
# Usage: curl -sSL <raw-url>/setup.sh | bash
#   or:  git clone ... && cd codebuddy2api && bash setup.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   CodeBuddy2API + OpenCode Config Setup         ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ---- Check prerequisites ----
info "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || error "python3 not found. Install Python 3.10+"
command -v node >/dev/null 2>&1 || error "node not found. Install Node.js 18+"
command -v npm >/dev/null 2>&1 || error "npm not found. Install Node.js 18+"
command -v git >/dev/null 2>&1 || error "git not found. Install git"

# Check for bun (optional but recommended for context-keeper)
if command -v bun >/dev/null 2>&1; then
    success "bun found"
    HAS_BUN=true
else
    warn "bun not found - context-keeper MCP won't work without it"
    warn "Install: curl -fsSL https://bun.sh/install | bash"
    HAS_BUN=false
fi

# Check for opencode
if command -v opencode >/dev/null 2>&1; then
    success "opencode CLI found"
else
    warn "opencode CLI not found"
    warn "Install: npm install -g opencode"
fi

success "Prerequisites OK"
echo ""

# ---- Setup Python venv for CodeBuddy2API ----
info "Setting up Python virtual environment..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    success "Created venv"
else
    success "venv already exists"
fi

source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
success "Python dependencies installed"
echo ""

# ---- Setup OpenCode Config ----
info "Setting up OpenCode configuration..."

OPENCODE_DIR="$HOME/.config/opencode"
BACKUP_DIR="$OPENCODE_DIR.backup.$(date +%Y%m%d_%H%M%S)"

# Backup existing config if present
if [ -d "$OPENCODE_DIR" ]; then
    warn "Existing OpenCode config found at $OPENCODE_DIR"
    read -p "  Backup and replace? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mv "$OPENCODE_DIR" "$BACKUP_DIR"
        success "Backed up to $BACKUP_DIR"
    else
        warn "Skipping OpenCode config setup (keeping existing)"
        SKIP_OPENCODE=true
    fi
fi

if [ "${SKIP_OPENCODE:-false}" = "false" ]; then
    mkdir -p "$OPENCODE_DIR"

    # Copy config files
    cp -r "$SCRIPT_DIR/opencode-config/"* "$OPENCODE_DIR/"

    # Install npm dependencies for opencode plugins
    info "Installing OpenCode plugin dependencies..."
    cd "$OPENCODE_DIR"
    npm install --silent 2>/dev/null || npm install
    success "OpenCode plugins installed"

    # Install bun deps for cli if bun available
    if [ "$HAS_BUN" = true ] && [ -f "$OPENCODE_DIR/cli/package.json" ]; then
        cd "$OPENCODE_DIR/cli"
        bun install --silent 2>/dev/null || true
    fi

    cd "$SCRIPT_DIR"
    success "OpenCode config installed to $OPENCODE_DIR"
fi

echo ""

# ---- Create .env template ----
info "Setting up environment..."

ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << 'ENVEOF'
# CodeBuddy2API Environment
# Copy this to .env and fill in your values

# GitHub Token (for MCP GitHub search)
GITHUB_TOKEN=ghp_your_token_here

# Gemini API Key (for contextplus embeddings)
GEMINI_API_KEY=your_gemini_api_key_here

# Exa API Key (optional - for web search)
EXA_API_KEY=your_exa_key_here

# EnowX Labs API Key (for opencode provider)
ENOWX_API_KEY=your_enowx_key_here

# CodeBuddy Direct API Key
CODEBUDDY_API_KEY=your_codebuddy_key_here
ENVEOF
    warn "Created .env template - EDIT THIS FILE with your actual keys!"
else
    success ".env already exists"
fi

echo ""

# ---- Patch opencode.json with actual API keys from .env ----
info "Configuring OpenCode with your API keys..."

if [ "${SKIP_OPENCODE:-false}" = "false" ]; then
    OPENCODE_JSON="$OPENCODE_DIR/opencode.json"
    if [ -f "$ENV_FILE" ]; then
        # Source env vars
        set -a
        source "$ENV_FILE" 2>/dev/null || true
        set +a

        # Replace placeholders in opencode.json
        if [ -n "$ENOWX_API_KEY" ] && [ "$ENOWX_API_KEY" != "your_enowx_key_here" ]; then
            sed -i.bak "s/YOUR_ENOWX_API_KEY_HERE/$ENOWX_API_KEY/g" "$OPENCODE_JSON" 2>/dev/null || \
            sed -i '' "s/YOUR_ENOWX_API_KEY_HERE/$ENOWX_API_KEY/g" "$OPENCODE_JSON"
            success "EnowX API key configured"
        else
            warn "EnowX API key not set - edit .env and re-run"
        fi

        if [ -n "$CODEBUDDY_API_KEY" ] && [ "$CODEBUDDY_API_KEY" != "your_codebuddy_key_here" ]; then
            sed -i.bak "s/YOUR_CODEBUDDY_API_KEY_HERE/$CODEBUDDY_API_KEY/g" "$OPENCODE_JSON" 2>/dev/null || \
            sed -i '' "s/YOUR_CODEBUDDY_API_KEY_HERE/$CODEBUDDY_API_KEY/g" "$OPENCODE_JSON"
            success "CodeBuddy API key configured"
        else
            warn "CodeBuddy API key not set - edit .env and re-run"
        fi

        # Fix $HOME paths to actual home
        sed -i.bak "s|\\\$HOME|$HOME|g" "$OPENCODE_JSON" 2>/dev/null || \
        sed -i '' "s|\\\$HOME|$HOME|g" "$OPENCODE_JSON"

        # Cleanup .bak files
        rm -f "$OPENCODE_JSON.bak"
    fi
fi

echo ""

# ---- Final summary ----
echo "╔══════════════════════════════════════════════════╗"
echo "║   Setup Complete!                               ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
success "CodeBuddy2API project ready"
success "OpenCode config installed"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your actual API keys"
echo "  2. Run: bash setup.sh  (again, to apply keys)"
echo "  3. Start CodeBuddy2API: bash start.sh"
echo "  4. Start OpenCode: opencode"
echo ""
echo "Required API keys:"
echo "  - GITHUB_TOKEN    : GitHub Personal Access Token"
echo "  - GEMINI_API_KEY  : Google AI Studio API key"
echo "  - ENOWX_API_KEY   : EnowX Labs API key"
echo "  - CODEBUDDY_API_KEY: CodeBuddy proxy key"
echo ""
info "For issues, check README.md"

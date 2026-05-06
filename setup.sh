#!/bin/bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info() { echo -e "${BLUE}▸${NC} $1"; }
ok() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
ask() { echo -e "${BOLD}$1${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

clear
echo ""
echo -e "${BOLD}  ┌─────────────────────────────────────────┐${NC}"
echo -e "${BOLD}  │  CodeBuddy2API — Quick Setup             │${NC}"
echo -e "${BOLD}  └─────────────────────────────────────────┘${NC}"
echo ""
echo "  Ini bakal setup:"
echo "    1. CodeBuddy2API server (Python)"
echo "    2. OpenCode AI config (opsional)"
echo ""

HAS_ERRORS=false

info "Checking system requirements..."
command -v python3 >/dev/null 2>&1 && ok "Python 3 $(python3 --version 2>&1 | cut -d' ' -f2)" || { fail "python3 not found — install dari https://python.org"; }
command -v node >/dev/null 2>&1 && ok "Node.js $(node --version)" || { warn "node not found — OpenCode config butuh ini"; HAS_ERRORS=true; }
command -v git >/dev/null 2>&1 && ok "git $(git --version | cut -d' ' -f3)" || { fail "git not found"; }
echo ""

echo -e "${BOLD}━━━ Step 1: CodeBuddy2API Server ━━━${NC}"
echo ""

if [ ! -d "venv" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
ok "Python dependencies installed"

if [ ! -f ".env" ]; then
    cp .env.example .env
    ok "Created .env from template"
    echo ""
    warn "PENTING: Edit file .env dan isi CODEBUDDY_PASSWORD"
    echo "    nano .env"
    echo ""
else
    ok ".env sudah ada"
fi
echo ""

echo -e "${BOLD}━━━ Step 2: OpenCode AI Config (Opsional) ━━━${NC}"
echo ""
echo "  OpenCode = AI coding assistant yang pake CodeBuddy2API"
echo "  sebagai backend. Config ini include 90+ skills, plugins,"
echo "  dan agent routing yang udah di-tune."
echo ""

read -p "  Install OpenCode config? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    if ! command -v node >/dev/null 2>&1; then
        fail "Node.js dibutuhkan untuk OpenCode. Install dulu: https://nodejs.org"
    fi

    OPENCODE_DIR="$HOME/.config/opencode"

    if [ -d "$OPENCODE_DIR" ] && [ -f "$OPENCODE_DIR/opencode.json" ]; then
        echo ""
        warn "OpenCode config sudah ada di $OPENCODE_DIR"
        read -p "  Overwrite? (backup otomatis) [y/N] " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            BACKUP="$OPENCODE_DIR.bak.$(date +%m%d_%H%M)"
            mv "$OPENCODE_DIR" "$BACKUP"
            ok "Backup: $BACKUP"
        else
            ok "Skip — config lama dipertahankan"
            SKIP_OC=true
        fi
    fi

    if [ "${SKIP_OC:-}" != "true" ]; then
        info "Copying config..."
        mkdir -p "$OPENCODE_DIR"
        cp -r "$SCRIPT_DIR/opencode-config/"* "$OPENCODE_DIR/"

        info "Installing plugins..."
        cd "$OPENCODE_DIR" && npm install --silent 2>/dev/null || npm install
        cd "$SCRIPT_DIR"

        if command -v bun >/dev/null 2>&1 && [ -f "$OPENCODE_DIR/cli/package.json" ]; then
            cd "$OPENCODE_DIR/cli" && bun install --silent 2>/dev/null || true
            cd "$SCRIPT_DIR"
        fi

        ok "OpenCode config installed"
        echo ""

        echo -e "${BOLD}  Sekarang configure API keys:${NC}"
        echo ""

        OPENCODE_JSON="$OPENCODE_DIR/opencode.json"

        read -p "  EnowX API Key (kosongkan kalau belum punya): " ENOWX_KEY
        if [ -n "$ENOWX_KEY" ]; then
            sed -i '' "s/YOUR_ENOWX_API_KEY_HERE/$ENOWX_KEY/g" "$OPENCODE_JSON" 2>/dev/null || \
            sed -i "s/YOUR_ENOWX_API_KEY_HERE/$ENOWX_KEY/g" "$OPENCODE_JSON"
            ok "EnowX key set"
        fi

        read -p "  CodeBuddy password (sama dengan CODEBUDDY_PASSWORD di .env): " CB_KEY
        if [ -n "$CB_KEY" ]; then
            sed -i '' "s/YOUR_CODEBUDDY_API_KEY_HERE/$CB_KEY/g" "$OPENCODE_JSON" 2>/dev/null || \
            sed -i "s/YOUR_CODEBUDDY_API_KEY_HERE/$CB_KEY/g" "$OPENCODE_JSON"
            ok "CodeBuddy key set"
        fi

        read -p "  GitHub Token (untuk search, kosongkan kalau skip): " GH_TOKEN
        if [ -n "$GH_TOKEN" ]; then
            echo "export GITHUB_TOKEN=$GH_TOKEN" >> "$HOME/.zshrc" 2>/dev/null || \
            echo "export GITHUB_TOKEN=$GH_TOKEN" >> "$HOME/.bashrc"
            ok "GitHub token added to shell profile"
        fi

        sed -i '' "s|\\\$HOME|$HOME|g" "$OPENCODE_JSON" 2>/dev/null || \
        sed -i "s|\\\$HOME|$HOME|g" "$OPENCODE_JSON"
        rm -f "$OPENCODE_JSON.bak"

        echo ""
        ok "OpenCode ready!"
    fi
else
    ok "Skipped OpenCode config"
fi

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}Setup selesai!${NC}"
echo ""
echo "  Langkah selanjutnya:"
echo ""
echo -e "  ${BOLD}1.${NC} Edit .env (kalau belum):"
echo "     nano .env"
echo ""
echo -e "  ${BOLD}2.${NC} Jalankan server:"
echo "     source venv/bin/activate && python web.py"
echo ""
echo -e "  ${BOLD}3.${NC} Buka browser → http://127.0.0.1:8003"
echo "     Login, tambah credential CodeBuddy"
echo ""
echo -e "  ${BOLD}4.${NC} Pake di OpenCode/ChatBox/client lain:"
echo "     Base URL: http://127.0.0.1:8003/codebuddy/v1"
echo "     API Key:  (password dari .env)"
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]] && [ "${SKIP_OC:-}" != "true" ]; then
    echo -e "  ${BOLD}5.${NC} Start OpenCode:"
    echo "     opencode"
    echo ""
fi

#!/bin/bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
info() { echo -e "${BLUE}▸${NC} $1"; }
ok() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
hint() { echo -e "  ${DIM}$1${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

clear
echo ""
echo -e "${BOLD}  ┌─────────────────────────────────────────┐${NC}"
echo -e "${BOLD}  │  CodeBuddy2API — Setup Otomatis          │${NC}"
echo -e "${BOLD}  └─────────────────────────────────────────┘${NC}"
echo ""
echo "  Setup ini bakal install CodeBuddy2API di komputer kamu."
echo "  Tinggal ikutin aja — semua otomatis."
echo ""
echo -e "  ${DIM}Tekan Ctrl+C kapan aja kalau mau batal.${NC}"
echo ""
read -p "  Lanjut? [Y/n] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "  Dibatalkan."
    exit 0
fi
echo ""

# ═══════════════════════════════════════════════════════════
# CEK SOFTWARE
# ═══════════════════════════════════════════════════════════

info "Mengecek software yang dibutuhkan..."
echo ""

MISSING=false

if command -v python3 >/dev/null 2>&1; then
    ok "Python $(python3 --version 2>&1 | cut -d' ' -f2)"
else
    echo -e "${RED}✗${NC} Python belum terinstall"
    hint "Download dari: https://www.python.org/downloads/"
    MISSING=true
fi

if command -v git >/dev/null 2>&1; then
    ok "Git $(git --version | cut -d' ' -f3)"
else
    echo -e "${RED}✗${NC} Git belum terinstall"
    hint "Download dari: https://git-scm.com/downloads"
    MISSING=true
fi

if command -v node >/dev/null 2>&1; then
    ok "Node.js $(node --version)"
    HAS_NODE=true
else
    warn "Node.js belum ada (opsional — cuma buat OpenCode)"
    hint "Download dari: https://nodejs.org/"
    HAS_NODE=false
fi

if [ "$MISSING" = true ]; then
    echo ""
    fail "Install software yang kurang dulu (lihat link di atas), lalu jalankan 'bash setup.sh' lagi."
fi

echo ""

# ═══════════════════════════════════════════════════════════
# STEP 1: INSTALL CODEBUDDY2API
# ═══════════════════════════════════════════════════════════

echo -e "${BOLD}━━━ Step 1/3: Install CodeBuddy2API ━━━${NC}"
echo ""

if [ ! -d "venv" ]; then
    info "Membuat environment Python..."
    python3 -m venv venv
fi

source venv/bin/activate
info "Installing dependencies (tunggu sebentar)..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
ok "Dependencies terinstall"
echo ""

# ═══════════════════════════════════════════════════════════
# STEP 2: SET PASSWORD
# ═══════════════════════════════════════════════════════════

echo -e "${BOLD}━━━ Step 2/3: Set Password ━━━${NC}"
echo ""

if [ ! -f ".env" ]; then
    cp .env.example .env
fi

echo "  Password ini buat mengakses API dari app lain."
echo "  Bebas isi apa aja — yang penting kamu ingat."
echo ""

CURRENT_PASS=$(grep "^CODEBUDDY_PASSWORD=" .env 2>/dev/null | cut -d'=' -f2)
if [ -z "$CURRENT_PASS" ]; then
    read -p "  Masukkan password: " USER_PASS
    if [ -n "$USER_PASS" ]; then
        sed -i '' "s/^CODEBUDDY_PASSWORD=.*/CODEBUDDY_PASSWORD=$USER_PASS/" .env 2>/dev/null || \
        sed -i "s/^CODEBUDDY_PASSWORD=.*/CODEBUDDY_PASSWORD=$USER_PASS/" .env
        ok "Password disimpan di file .env"
    else
        warn "Password kosong — isi nanti di file .env"
    fi
else
    ok "Password sudah ada: $CURRENT_PASS"
fi
echo ""

# ═══════════════════════════════════════════════════════════
# STEP 3: OPENCODE CONFIG (OPSIONAL)
# ═══════════════════════════════════════════════════════════

echo -e "${BOLD}━━━ Step 3/3: OpenCode AI Config (Opsional) ━━━${NC}"
echo ""
echo "  OpenCode = AI assistant di terminal yang bisa:"
echo "    • Chat dengan AI (Claude, GPT, Gemini)"
echo "    • Edit code otomatis"
echo "    • Jalankan command"
echo ""
echo "  Kalau kamu cuma mau pake CodeBuddy2API di ChatBox"
echo "  atau app lain, skip aja bagian ini."
echo ""

read -p "  Install OpenCode config? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ "$HAS_NODE" = false ]; then
        echo ""
        warn "Node.js dibutuhkan untuk OpenCode."
        hint "Install dari: https://nodejs.org/"
        hint "Setelah install Node.js, jalankan 'bash setup.sh' lagi."
        echo ""
    else
        OPENCODE_DIR="$HOME/.config/opencode"

        if [ -d "$OPENCODE_DIR" ] && [ -f "$OPENCODE_DIR/opencode.json" ]; then
            echo ""
            warn "OpenCode config sudah ada."
            read -p "  Timpa dengan yang baru? (yang lama di-backup) [y/N] " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                BACKUP="$OPENCODE_DIR.backup-$(date +%m%d_%H%M)"
                mv "$OPENCODE_DIR" "$BACKUP"
                ok "Backup disimpan di: $BACKUP"
            else
                ok "Config lama dipertahankan"
                SKIP_OC=true
            fi
        fi

        if [ "${SKIP_OC:-}" != "true" ]; then
            echo ""
            info "Meng-copy config..."
            mkdir -p "$OPENCODE_DIR"
            cp -r "$SCRIPT_DIR/opencode-config/"* "$OPENCODE_DIR/"

            info "Installing plugins..."
            cd "$OPENCODE_DIR" && npm install --silent 2>/dev/null || npm install
            cd "$SCRIPT_DIR"

            if command -v bun >/dev/null 2>&1 && [ -f "$OPENCODE_DIR/cli/package.json" ]; then
                cd "$OPENCODE_DIR/cli" && bun install --silent 2>/dev/null || true
                cd "$SCRIPT_DIR"
            fi

            ok "OpenCode config terinstall"
            echo ""

            echo "  Sekarang masukkan API keys untuk OpenCode."
            echo "  (Kosongkan kalau belum punya — bisa diisi nanti)"
            echo ""

            OPENCODE_JSON="$OPENCODE_DIR/opencode.json"

            echo -e "  ${DIM}EnowX API Key = key dari provider AI model${NC}"
            read -p "  EnowX API Key: " ENOWX_KEY
            if [ -n "$ENOWX_KEY" ]; then
                sed -i '' "s/YOUR_ENOWX_API_KEY_HERE/$ENOWX_KEY/g" "$OPENCODE_JSON" 2>/dev/null || \
                sed -i "s/YOUR_ENOWX_API_KEY_HERE/$ENOWX_KEY/g" "$OPENCODE_JSON"
                ok "EnowX key disimpan"
            fi

            echo ""
            echo -e "  ${DIM}CodeBuddy password = sama dengan yang kamu set di Step 2${NC}"
            read -p "  CodeBuddy password: " CB_KEY
            if [ -n "$CB_KEY" ]; then
                sed -i '' "s/YOUR_CODEBUDDY_API_KEY_HERE/$CB_KEY/g" "$OPENCODE_JSON" 2>/dev/null || \
                sed -i "s/YOUR_CODEBUDDY_API_KEY_HERE/$CB_KEY/g" "$OPENCODE_JSON"
                ok "CodeBuddy key disimpan"
            fi

            echo ""
            echo -e "  ${DIM}GitHub Token = buat search code di GitHub (opsional)${NC}"
            echo -e "  ${DIM}Buat di: github.com > Settings > Developer settings > Tokens${NC}"
            read -p "  GitHub Token (kosongkan kalau skip): " GH_TOKEN
            if [ -n "$GH_TOKEN" ]; then
                if [ -f "$HOME/.zshrc" ]; then
                    echo "export GITHUB_TOKEN=$GH_TOKEN" >> "$HOME/.zshrc"
                elif [ -f "$HOME/.bashrc" ]; then
                    echo "export GITHUB_TOKEN=$GH_TOKEN" >> "$HOME/.bashrc"
                fi
                ok "GitHub token disimpan di shell profile"
            fi

            sed -i '' "s|\\\$HOME|$HOME|g" "$OPENCODE_JSON" 2>/dev/null || \
            sed -i "s|\\\$HOME|$HOME|g" "$OPENCODE_JSON"
            rm -f "$OPENCODE_JSON.bak"

            echo ""
            ok "OpenCode siap digunakan!"

            if ! command -v opencode >/dev/null 2>&1; then
                echo ""
                hint "Install OpenCode CLI: npm install -g opencode"
                hint "Setelah install, ketik 'opencode' di terminal untuk mulai."
            fi
        fi
    fi
else
    ok "OpenCode di-skip"
fi

# ═══════════════════════════════════════════════════════════
# SELESAI
# ═══════════════════════════════════════════════════════════

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}${BOLD}Setup selesai!${NC}"
echo ""
echo "  Langkah selanjutnya:"
echo ""
echo -e "  ${BOLD}1.${NC} Jalankan server:"
echo "     source venv/bin/activate && python web.py"
echo ""
echo -e "  ${BOLD}2.${NC} Buka browser → http://127.0.0.1:8003"
echo "     Login, lalu tambah akun CodeBuddy di tab Credentials"
echo ""
echo -e "  ${BOLD}3.${NC} Pake di app AI:"
echo "     Base URL: http://127.0.0.1:8003/codebuddy/v1"
echo "     API Key:  (password yang kamu set tadi)"
echo "     Model:    auto-chat"
echo ""
echo -e "  ${DIM}Butuh bantuan? Baca README.md${NC}"
echo ""

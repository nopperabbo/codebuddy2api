# CodeBuddy2API

OpenAI-compatible API wrapper untuk CodeBuddy. Bisa dipake di ChatBox, OpenCode, LobeChat, atau client apapun yang support OpenAI API format.

## Quick Start

```bash
git clone https://github.com/nopperabbo/codebuddy2api.git
cd codebuddy2api
bash setup.sh
```

Script interaktif — tinggal jawab pertanyaan, semua otomatis.

---

## Manual Setup (kalau ga mau pake script)

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Config

```bash
cp .env.example .env
nano .env
```

Yang **wajib** diisi: `CODEBUDDY_PASSWORD` (password bebas, buat akses API).

### 3. Jalankan

```bash
source venv/bin/activate
python web.py
```

### 4. Tambah Credential

1. Buka `http://127.0.0.1:8003`
2. Login pake password dari `.env`
3. Tab "Credential Management" → "Start Authentication"
4. Login ke akun CodeBuddy
5. Done — credential otomatis tersimpan

---

## Pake di Client

| Setting | Value |
|---------|-------|
| Base URL | `http://127.0.0.1:8003/codebuddy/v1` |
| API Key | password dari `.env` |
| Model | `auto-chat` (recommended) |

### Model Tersedia

| Model | Keterangan |
|-------|------------|
| `auto-chat` | Auto pilih model terbaik |
| `auto-smart` | Prioritas kualitas |
| `auto-fast` | Prioritas kecepatan |
| `claude-opus-4.6` | Claude Opus 4.6 |
| `gpt-5.5` | GPT-5.5 |
| `gpt-5` | GPT-5 |
| `gemini-2.5-pro` | Gemini 2.5 Pro |
| `gemini-3.1-pro` | Gemini 3.1 Pro |
| `o4-mini` | O4 Mini |
| `claude-haiku-4.5` | Claude Haiku 4.5 |

### Contoh Python

```python
import openai

client = openai.OpenAI(
    api_key="password_kamu",
    base_url="http://127.0.0.1:8003/codebuddy/v1"
)

response = client.chat.completions.create(
    model="auto-chat",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

---

## OpenCode AI Config (Bonus)

Repo ini juga include full config untuk [OpenCode](https://opencode.ai/) — AI coding assistant yang pake CodeBuddy2API sebagai backend.

**Apa yang termasuk:**
- 42 specialized AI agents (debugger, reviewer, architect, dll)
- 90+ skills (DevOps, frontend, backend, security, dll)
- Custom plugins (auto-checkpoint, git-safety, context-keeper)
- Model routing & profiles
- MCP server configs (GitHub, Playwright, memory, dll)

**Install:** Jalankan `bash setup.sh` dan jawab "y" waktu ditanya soal OpenCode.

**Prerequisites tambahan:**
- Node.js 18+ (`node --version`)
- Bun (`curl -fsSL https://bun.sh/install | bash`)
- OpenCode CLI (`npm install -g opencode`)

Detail config: lihat [`opencode-config/README.md`](opencode-config/README.md)

---

## Docker

```bash
docker-compose up -d
```

Atau manual:
```bash
docker build -t codebuddy2api .
docker run -d -p 8003:8003 --env-file .env codebuddy2api
```

---

## Akses dari Device Lain (Satu WiFi)

1. Set `CODEBUDDY_HOST=0.0.0.0` di `.env`
2. Cek IP: `ifconfig` (Mac) / `ipconfig` (Windows)
3. Akses: `http://IP_KAMU:8003/codebuddy/v1`

---

## Troubleshooting

| Error | Solusi |
|-------|--------|
| "No valid credentials" | Buka web admin, tambah credential via OAuth |
| "Invalid password" | API key di client ga match `CODEBUDDY_PASSWORD` |
| "401/403" | Credential expired — hapus & login ulang di web admin |
| Port conflict | Ganti `CODEBUDDY_PORT` di `.env` |

---

## Struktur Project

```
codebuddy2api/
├── web.py                  # Entry point (FastAPI)
├── config.py               # Config management
├── src/                    # Source code
│   ├── codebuddy_router.py     # /v1/chat/completions
│   ├── codebuddy_api_client.py # Client ke CodeBuddy
│   ├── codebuddy_token_manager.py # Credential rotation
│   └── ...
├── frontend/               # Web admin UI
├── opencode-config/        # OpenCode AI config (opsional)
├── setup.sh                # One-click setup script
├── start.sh                # Start server (Linux/Mac)
├── start.bat               # Start server (Windows)
├── .env.example            # Template config
├── Dockerfile              # Docker image
└── docker-compose.yml      # Docker Compose
```

---

## License

MIT

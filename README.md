# CodeBuddy2API

Wrapper CodeBuddy API menjadi format OpenAI-compatible. Bisa dipake di semua client yang support OpenAI API (ChatBox, OpenCode, LobeChat, dll).

## Fitur

- OpenAI-compatible endpoint (`/v1/chat/completions`)
- Streaming & non-streaming support
- Multi-credential rotation (bisa pake banyak akun CodeBuddy)
- Web admin panel untuk manage credentials
- Auto OAuth login via browser
- Docker support
- Keyword filtering/replacement

---

## Cara Install & Running

### Prerequisite

- **Python 3.8+** (cek: `python3 --version`)
- **Git** (cek: `git --version`)
- **Akun CodeBuddy** (daftar di [codebuddy.ai](https://www.codebuddy.ai))

---

### Step 1: Clone Repo

```bash
git clone https://github.com/nopperabbo/codebuddy2api.git
cd codebuddy2api
```

### Step 2: Buat Virtual Environment & Install Dependencies

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Atau langsung pake script otomatis:
- **Windows:** double-click `start.bat`
- **macOS/Linux:** `chmod +x start.sh && ./start.sh`

### Step 3: Setup Config

Copy file `.env.example` jadi `.env`:

```bash
cp .env.example .env
```

Edit file `.env` — yang **WAJIB** diisi cuma 1:

```env
CODEBUDDY_PASSWORD=password_bebas_buat_akses_api
```

Ini password untuk akses API service kamu. Nanti client connect pake password ini.

**Config lengkap (opsional):**

| Variable | Default | Keterangan |
|----------|---------|------------|
| `CODEBUDDY_PASSWORD` | *(wajib)* | Password untuk akses API |
| `CODEBUDDY_HOST` | `127.0.0.1` | Host server |
| `CODEBUDDY_PORT` | `8001` | Port server |
| `CODEBUDDY_LOG_LEVEL` | `INFO` | Level log (DEBUG/INFO/WARNING/ERROR) |
| `CODEBUDDY_MODELS` | *(list panjang)* | Model yang tersedia |
| `CODEBUDDY_PROMPT_ENHANCE` | `true` | Auto enhance prompt |

### Step 4: Jalankan Server

```bash
# Pastikan venv aktif
source venv/bin/activate   # Linux/macOS
# atau: venv\Scripts\activate  # Windows

python web.py
```

Server jalan di `http://127.0.0.1:8001`

### Step 5: Tambah Credential CodeBuddy

1. Buka browser, akses `http://127.0.0.1:8001`
2. Login pake password yang kamu set di `.env` (`CODEBUDDY_PASSWORD`)
3. Masuk tab **"Credential Management"**
4. Klik **"Start Authentication"** / **"开始认证"**
5. Akan muncul link login CodeBuddy — klik dan login pake akun CodeBuddy kamu
6. Setelah login berhasil, credential otomatis tersimpan
7. Klik **"Refresh"** untuk lihat credential baru

> Bisa tambah banyak credential untuk rotation (biar ga kena rate limit).

---

## Cara Pake di Client

### Base URL

```
http://127.0.0.1:8001/codebuddy/v1
```

### API Key

Isi dengan `CODEBUDDY_PASSWORD` yang kamu set di `.env`.

### Model yang Tersedia

- `claude-opus-4.6`
- `gpt-5.5`
- `gpt-5`
- `gpt-5-mini`
- `gpt-5-nano`
- `o4-mini`
- `gemini-2.5-pro`
- `gemini-2.5-flash`
- `gemini-3.1-pro`
- `claude-haiku-4.5`
- `auto-chat` (recommended — auto pilih model terbaik)
- `auto-smart`
- `auto-fast`
- `auto-cheap`

### Contoh: Python

```python
import openai

client = openai.OpenAI(
    api_key="password_kamu",
    base_url="http://127.0.0.1:8001/codebuddy/v1"
)

response = client.chat.completions.create(
    model="auto-chat",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

### Contoh: curl

```bash
curl -X POST "http://127.0.0.1:8001/codebuddy/v1/chat/completions" \
  -H "Authorization: Bearer password_kamu" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto-chat",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Contoh: Di ChatBox / LobeChat / OpenCode

- **API Base URL:** `http://127.0.0.1:8001/codebuddy/v1`
- **API Key:** password yang kamu set di `.env`
- **Model:** pilih dari list di atas

---

## Running dengan Docker

```bash
# Build & run
docker-compose up -d

# Atau manual
docker build -t codebuddy2api .
docker run -d -p 8001:8001 --env-file .env codebuddy2api
```

---

## Struktur Project

```
codebuddy2api/
├── web.py                         # Entry point (FastAPI server)
├── config.py                      # Config management
├── src/
│   ├── codebuddy_router.py        # Main API router (/v1/chat/completions)
│   ├── codebuddy_api_client.py    # Client ke CodeBuddy API
│   ├── codebuddy_token_manager.py # Credential rotation
│   ├── codebuddy_auth_router.py   # OAuth login flow
│   ├── frontend_router.py         # Web admin panel
│   ├── auth.py                    # Password auth middleware
│   ├── keyword_replacer.py        # Keyword filtering
│   ├── prompt_enhancer.py         # Prompt enhancement
│   ├── context_manager.py         # Context/session management
│   ├── session_memory.py          # Session memory
│   ├── model_router.py            # Model routing
│   ├── settings_router.py         # Settings API
│   └── usage_stats_manager.py     # Usage statistics
├── frontend/
│   └── admin.html                 # Web admin UI
├── config/
│   └── filters.json               # Keyword replacement rules
├── .codebuddy_creds/              # Credential storage (gitignored)
├── .env.example                   # Template environment config
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Docker image
├── docker-compose.yml             # Docker Compose config
├── start.bat                      # Windows start script
├── start.sh                       # Linux/macOS start script
├── bulk_harvest.py                # Bulk credential harvester
└── tests/                         # Test files
```

---

## Troubleshooting

### "No valid CodeBuddy credentials found"
→ Belum ada credential. Buka web admin (`http://127.0.0.1:8001`) dan tambah credential via OAuth.

### "Invalid password"
→ API key yang kamu pake di client ga match sama `CODEBUDDY_PASSWORD` di `.env`.

### "API error: 401/403"
→ Credential CodeBuddy expired. Buka web admin, hapus yang expired, dan login ulang.

### Server ga bisa diakses dari device lain
→ Ganti `CODEBUDDY_HOST=0.0.0.0` di `.env` supaya listen di semua interface.

### Port 8001 sudah dipakai
→ Ganti `CODEBUDDY_PORT=8002` (atau port lain) di `.env`.

---

## Akses dari HP / Device Lain (Satu WiFi)

1. Set `CODEBUDDY_HOST=0.0.0.0` di `.env`
2. Cek IP komputer kamu: `ifconfig` (Mac) atau `ipconfig` (Windows)
3. Dari device lain, akses: `http://IP_KOMPUTER:8001/codebuddy/v1`

---

## License

MIT

# CodeBuddy2API + Kiro Gateway

> OpenAI-compatible proxy for **CodeBuddy** and **Kiro (Amazon Q Developer)** — access Claude Opus 4.7, Sonnet 4.5, GLM-5, Qwen3, and more via a single local API.

---

## ✨ Features

- 🔑 **Kiro Gateway** — Use `ksk_` API keys from Kiro IDE to access Claude models via AWS
- 🤖 **10+ AI Models** — Claude Opus 4.7, Opus 4.5, Sonnet 4.5, Haiku 4.5, GLM-5, Qwen3, Minimax, and more
- 🔄 **Key Rotation** — Automatic round-robin across multiple API keys
- 📡 **OpenAI-Compatible** — Works with OpenCode, Cursor, Continue, and any OpenAI-compatible client
- 🌊 **Streaming Support** — Real-time SSE streaming responses
- 🛡️ **Error Recovery** — Auto-retry with key rotation on 403/429 errors

---

## 📋 Prerequisites

- **Python 3.10+**
- **Kiro IDE account** (free) — to get your `ksk_` API key
- **Git**

---

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/nopperabbo/codebuddy2api.git
cd codebuddy2api
```

### 2. Set Up Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set your password:

```env
CODEBUDDY_PASSWORD=your_secret_password_here
```

### 5. Add Your Kiro API Key(s)

Create `kiro_keys.json` in the project root:

```json
[
  {"api_key": "ksk_YOUR_FIRST_KEY_HERE"},
  {"api_key": "ksk_YOUR_SECOND_KEY_HERE"}
]
```

> 💡 **How to get your `ksk_` key:** Open [Kiro IDE](https://kiro.dev), sign in, then find your API key in Settings → API Keys. It starts with `ksk_`.

### 6. Start the Server

```bash
bash start.sh
```

The server will start on `http://localhost:8003`.

---

## 🎯 Available Models (Kiro Gateway)

| Model ID | Description | Status |
|---|---|---|
| `claude-opus-4.7` | **Claude Opus 4.7** — Latest & most capable | ✅ |
| `claude-opus-4.5` | Claude Opus 4.5 | ✅ |
| `claude-sonnet-4.5` | Claude Sonnet 4.5 | ✅ |
| `claude-haiku-4.5` | Claude Haiku 4.5 — Fast & light | ✅ |
| `claude-sonnet-4` | Claude Sonnet 4 | ✅ |
| `glm-5` | GLM-5 (via Kiro) | ✅ |
| `qwen3-coder-next` | Qwen3 Coder Next (via Kiro) | ✅ |
| `minimax-m2.5` | Minimax M2.5 (via Kiro) | ✅ |
| `minimax-m2.1` | Minimax M2.1 (via Kiro) | ✅ |
| `auto` | Let Kiro pick the best model | ✅ |

---

## 🔗 API Endpoints

### Kiro Gateway

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/kiro/v1/models` | List available Kiro models |
| `POST` | `/kiro/v1/chat/completions` | Chat completions (OpenAI-compatible) |
| `GET` | `/kiro/v1/keys` | List configured API keys (masked) |
| `POST` | `/kiro/v1/keys` | Add a new API key |

### CodeBuddy (Original)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/codebuddy/v1/models` | List CodeBuddy models |
| `POST` | `/codebuddy/v1/chat/completions` | Chat completions |
| `GET` | `/codebuddy/v1/credentials` | List credentials |

---

## 🧪 Quick Test

### Test with curl

```bash
# List models
curl -s -H "Authorization: Bearer YOUR_PASSWORD" \
  http://localhost:8003/kiro/v1/models | python3 -m json.tool

# Chat with Opus 4.7
curl -s -X POST http://localhost:8003/kiro/v1/chat/completions \
  -H "Authorization: Bearer YOUR_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4.7",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'

# Streaming
curl -N -X POST http://localhost:8003/kiro/v1/chat/completions \
  -H "Authorization: Bearer YOUR_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4.7",
    "messages": [{"role": "user", "content": "Write a haiku about coding"}],
    "stream": true
  }'
```

---

## 🛠️ Integration with OpenCode

Add this to your `~/.config/opencode/opencode.json` under the `"provider"` section:

```json
"kiro": {
  "models": {
    "claude-opus-4.7": {
      "limit": { "context": 200000, "output": 64000 },
      "name": "Claude Opus 4.7 (Kiro/AWS)",
      "modalities": {
        "input": ["text", "image", "pdf"],
        "output": ["text"]
      },
      "variants": {
        "low": { "thinkingConfig": { "thinkingBudget": 16384 } },
        "medium": { "thinkingConfig": { "thinkingBudget": 32768 } },
        "high": { "thinkingConfig": { "thinkingBudget": 65536 } },
        "max": { "thinkingConfig": { "thinkingBudget": 128000 } }
      }
    },
    "claude-opus-4.5": {
      "limit": { "context": 200000, "output": 64000 },
      "name": "Claude Opus 4.5 (Kiro/AWS)",
      "modalities": {
        "input": ["text", "image", "pdf"],
        "output": ["text"]
      },
      "variants": {
        "low": { "thinkingConfig": { "thinkingBudget": 16384 } },
        "medium": { "thinkingConfig": { "thinkingBudget": 32768 } },
        "high": { "thinkingConfig": { "thinkingBudget": 65536 } },
        "max": { "thinkingConfig": { "thinkingBudget": 128000 } }
      }
    },
    "claude-sonnet-4": {
      "limit": { "context": 200000, "output": 64000 },
      "name": "Claude Sonnet 4 (Kiro/AWS)",
      "modalities": {
        "input": ["text", "image", "pdf"],
        "output": ["text"]
      },
      "variants": {
        "low": { "thinkingConfig": { "thinkingBudget": 8192 } },
        "medium": { "thinkingConfig": { "thinkingBudget": 16384 } },
        "high": { "thinkingConfig": { "thinkingBudget": 24576 } },
        "max": { "thinkingConfig": { "thinkingBudget": 32768 } }
      }
    },
    "auto": {
      "limit": { "context": 200000, "output": 64000 },
      "name": "Auto (Kiro/AWS Best Pick)",
      "modalities": {
        "input": ["text", "image", "pdf"],
        "output": ["text"]
      },
      "variants": {
        "low": { "thinkingConfig": { "thinkingBudget": 8192 } },
        "medium": { "thinkingConfig": { "thinkingBudget": 16384 } },
        "high": { "thinkingConfig": { "thinkingBudget": 24576 } },
        "max": { "thinkingConfig": { "thinkingBudget": 32768 } }
      }
    }
  },
  "name": "Kiro (Amazon Q)",
  "npm": "@ai-sdk/openai-compatible",
  "options": {
    "apiKey": "YOUR_PASSWORD",
    "baseURL": "http://127.0.0.1:8003/kiro/v1"
  }
}
```

Then select `kiro/claude-opus-4.7` as your model in OpenCode.

---

## 🔧 Integration with Cursor / Continue / Other Tools

Use these settings in any OpenAI-compatible client:

| Setting | Value |
|---|---|
| **Base URL** | `http://localhost:8003/kiro/v1` |
| **API Key** | Your `CODEBUDDY_PASSWORD` from `.env` |
| **Model** | `claude-opus-4.7` (or any from the list above) |

---

## 📁 Project Structure

```
codebuddy2api/
├── src/
│   ├── __init__.py
│   ├── auth.py              # Authentication middleware
│   ├── codebuddy_router.py  # CodeBuddy proxy router
│   ├── kiro_api_client.py   # Kiro API client & model mapping
│   ├── kiro_router.py       # Kiro gateway router
│   └── ...
├── kiro_keys.json           # Your ksk_ API keys (gitignored)
├── .env                     # Environment config (gitignored)
├── .env.example             # Example environment file
├── requirements.txt         # Python dependencies
├── start.sh                 # Startup script
└── web.py                   # Main application entry point
```

---

## ⚠️ Important Notes

- **Keep your `ksk_` keys safe** — they provide direct access to the Kiro API
- **`kiro_keys.json` is gitignored** — your keys will never be accidentally committed
- The server runs on port `8003` by default
- All requests require the `Authorization: Bearer YOUR_PASSWORD` header
- Multiple `ksk_` keys are supported — the server rotates through them automatically

---

## 🤝 Credits

- [kiro-gateway](https://github.com/jwadow/kiro-gateway) — Reference implementation for Kiro API integration
- [Amazon Q Developer](https://aws.amazon.com/q/developer/) — The underlying AI service

---

## 📄 License

MIT

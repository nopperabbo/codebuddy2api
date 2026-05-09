# OpenCode Configuration

Config ini di-install otomatis oleh `setup.sh` ke `~/.config/opencode/`.

**Jangan edit file di folder ini** — edit yang di `~/.config/opencode/` setelah install.

## Struktur

```
opencode-config/
├── opencode.json          ← Config utama (provider, MCP servers, LSP)
├── AGENTS.md              ← System prompt untuk AI agent
├── agents.json            ← 42 agent roles (debugger, reviewer, dll)
├── oh-my-openagent.json   ← Model routing per-agent
├── dcp.jsonc              ← Context pruning settings
├── package.json           ← Plugin dependencies
├── plugins/               ← Custom plugins (auto-checkpoint, git-safety, dll)
├── skills/                ← 90+ AI skills (DevOps, frontend, backend, dll)
├── profiles/              ← Model profiles (quality vs speed vs budget)
├── prompts/               ← Prompt templates
└── cli/                   ← Context-keeper MCP server
```

## Yang Perlu Diisi Manual

Setelah install, edit `~/.config/opencode/opencode.json`:

1. **EnowX API Key** — ganti `YOUR_ENOWX_API_KEY_HERE`
2. **CodeBuddy password** — ganti `YOUR_CODEBUDDY_API_KEY_HERE` (sama dengan password di .env)

Atau biar `setup.sh` yang handle — dia bakal nanya interaktif.

## Environment Variables

Set di shell profile (`~/.zshrc` atau `~/.bashrc`):

```bash
export GITHUB_TOKEN=ghp_xxx        # Untuk GitHub MCP search
export GEMINI_API_KEY=AIza_xxx     # Untuk contextplus embeddings
export EXA_API_KEY=xxx             # Opsional — web search
```

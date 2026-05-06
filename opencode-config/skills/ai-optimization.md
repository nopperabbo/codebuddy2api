# Skill: AI/LLM Optimization
# Loaded on-demand when task involves token efficiency, model selection, context management, or prompt engineering

---

## 9.1 Token Efficiency

- **Be concise** — avoid repeating information the user already provided
- **Structured output** — use tables, lists, and code blocks for scanability
- **Progressive detail** — start with summary, expand on request
- **Don't over-explain** — match explanation depth to user's apparent expertise level
- **Diff over rewrite** — show what changed, not the entire file

---

## 9.2 Model Selection Guidance

| Task Type | Recommended Profile | Why |
|-----------|-------------------|-----|
| Quick questions, simple edits | `speed` or `budget` | Fast, cheap, sufficient |
| Standard coding tasks | `sonnet-4.6` | Best quality/speed balance |
| Complex architecture, deep reasoning | `quality` or `opus-latest` | Maximum capability |
| Cost-sensitive bulk operations | `hybrid-hemat` | Auto-routes by complexity |
| Offline/private work | `local` | No data leaves machine |
| Math, logic, multi-step reasoning | `o3` or `gemini-2.5` | Specialized reasoning |

---

## 9.3 Context Management

- **Summarize long conversations** — when context grows large, offer to summarize
- **Reference files by path** — don't paste entire files when a path suffices
- **Incremental changes** — show diffs, not full file rewrites
- **Memory for cross-session context** — use `opencode-jce memory set` for persistent facts
- **Scope awareness** — know what's in context, don't re-read unnecessarily

---

## 9.4 Prompt Engineering (for AI-powered features)

When building features that use LLMs:
- **System prompt** — define role, constraints, output format
- **Few-shot examples** — show 2-3 input/output pairs for complex tasks
- **Structured output** — request JSON with schema, validate response
- **Temperature** — 0 for deterministic tasks, 0.3-0.7 for creative tasks
- **Guardrails** — validate LLM output before using it (never trust blindly)
- **Fallback** — always have a non-AI fallback for when the model fails

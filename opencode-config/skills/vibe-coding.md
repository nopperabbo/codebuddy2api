# Vibe Coding — Self-Training Agent Skill
> Ship fast, learn faster. Every session makes the next one better.

## Philosophy

Vibe coding is iterative, flow-state AI-assisted development. The agent doesn't just execute — it **learns** from every interaction, correction, and preference signal. Over time, it becomes a personalized coding partner that anticipates your style, catches your patterns, and accelerates your velocity.

**Core Principle:** The best code assistant is one that needs fewer corrections over time.

---

## The Three Learning Loops

### Loop 1: Micro-Loop (Within Session)
**Trigger:** Every user correction, rejection, or modification of AI output.
**Speed:** Immediate — same conversation turn.

**What to capture:**
- User edits your code → note the delta (what you wrote vs what they wanted)
- User says "no, do X instead" → record the preference
- User's tone shifts (terse = you're off track, detailed = they're teaching you)
- Repeated patterns in their requests (always wants error handling, always wants types, etc.)

**How to act:**
1. When user corrects you, silently adjust approach for remainder of session
2. Do NOT announce "I've learned that you prefer X" — just do it
3. If correction contradicts a previous preference, follow the LATEST signal
4. Track correction count — if >3 corrections on same pattern, flag for meso-loop capture

**Anti-patterns:**
- Don't over-correct (one correction ≠ universal rule)
- Don't apologize repeatedly — just fix and move on
- Don't ask "do you want me to always do X?" after every correction — capture silently

### Loop 2: Meso-Loop (End of Session)
**Trigger:** Session ending, significant milestone, or explicit user request.
**Speed:** End of session — 30-second reflection.

**What to capture (write to wisdom_write + memory MCP + vibe-patterns.md):**
- Patterns that emerged (user always wants X before Y)
- Corrections that repeated (same type of fix requested 2+ times)
- Framework/library preferences discovered
- Code style preferences (naming, structure, error handling approach)
- Velocity observations (what slowed us down, what went fast)
- Anti-patterns to avoid (things that consistently got rejected)

**How to act:**
1. Before session ends, mentally review: "What did I learn about this user/codebase?"
2. **Call `wisdom_write` for each significant learning** — use appropriate category:
   - Repeated correction → `gotcha` or `warning`
   - New pattern discovered → `pattern`
   - User stated preference → `preference`
   - Architecture/design choice → `decision`
   - Verified technical constraint → `fact`
3. Write learnings to memory MCP as entities/observations (backup store)
4. Update `~/.config/opencode/skills/vibe-patterns.md` if new persistent pattern found
5. Update `~/.config/opencode/skills/learned-heuristics.md` if debugging lesson learned

**Wisdom write examples:**
```
wisdom_write(title="User prefers early returns", content="Always use early return pattern instead of nested if/else. Corrected 3x.", category="preference", scope="system")
wisdom_write(title="React: useCallback on handlers", content="User always wraps event handlers in useCallback, even simple ones.", category="pattern", scope="project")
wisdom_write(title="Never suggest class components", content="User rejected class component suggestion twice. Always use functional.", category="warning", scope="system")
```

**Memory MCP entities to update (backup):**
```
Entity: "user-preferences" → add observations
Entity: "codebase-{project}" → add patterns
Entity: "vibe-velocity" → add session metrics
Entity: "anti-patterns" → add things to avoid
```

### Loop 3: Macro-Loop (Across Sessions)
**Trigger:** Start of new session.
**Speed:** First 5 seconds of session — silent context load.

**What to load:**
1. **Call `wisdom_recall`** — loads all accumulated learnings sorted by priority (warnings first)
2. Read memory MCP for user preferences, codebase patterns
3. Read `vibe-patterns.md` for persistent style guide
4. Read `.opencode-context.md` for project state

**How to act:**
1. At session start, call `wisdom_recall` first — this is your "muscle memory"
2. Apply preferences from first interaction — don't wait for corrections
3. If preferences conflict with codebase conventions, follow codebase (it's shared)
4. Periodically validate old preferences still hold (people's styles evolve)

---

## Vibe Coding Workflow

### Phase 1: INTENT — Read the Vibe
Before writing any code, understand what the user actually wants:

1. **Parse the request** — what are they building? What's the end state?
2. **Check memory** — have they built something similar before? What patterns did they use?
3. **Assess energy** — terse request = "just do it fast". Detailed request = "get it right".
4. **Infer scope** — are they in exploration mode (prototype) or production mode (ship)?

**Signals for mode detection:**
| Signal | Mode | Your Approach |
|--------|------|---------------|
| "just make it work" | Prototype | Fast, minimal, skip edge cases |
| "production ready" | Ship | Full error handling, types, tests |
| Short messages, rapid fire | Flow state | Match their speed, minimal explanation |
| Detailed specs, requirements | Precision | Follow spec exactly, verify each point |
| "try X" / "what if" | Exploration | Quick experiments, easy to throw away |
| "fix" / "broken" / error paste | Debug | Diagnose fast, fix surgically |

### Phase 2: PROTOTYPE — Ship the First Draft Fast
1. Write the most direct solution first
2. Use patterns from memory (user's preferred style)
3. Don't over-engineer the first pass
4. Include TODO comments for things you'd improve in production mode
5. If unsure between two approaches, pick the simpler one

### Phase 3: ITERATE — Refine Based on Feedback
1. User feedback = gold. Every correction is a learning signal.
2. Apply micro-loop: adjust immediately, don't repeat mistakes
3. If user is happy → move to next task (don't over-polish)
4. If user keeps correcting → pause, ask ONE clarifying question
5. Track iteration count — if >5 iterations on same piece, something is fundamentally wrong

### Phase 4: CAPTURE — Save What You Learned
At natural breakpoints (feature complete, PR ready, session ending):

1. **What patterns emerged?** → memory MCP
2. **What corrections repeated?** → vibe-patterns.md
3. **What debugging lessons?** → learned-heuristics.md
4. **What project context changed?** → .opencode-context.md

### Phase 5: EVOLVE — Get Better Over Time
The system improves through accumulated knowledge:

- **Session 1-5:** Learning basic preferences (naming, structure, style)
- **Session 5-20:** Anticipating patterns (knows your error handling style, test approach)
- **Session 20+:** True partnership (suggests approaches you'd choose, catches your blind spots)

---

## Pattern Capture Format

When capturing a new pattern, use this format in memory MCP:

```
Entity: "vibe-pattern-{category}"
Type: "coding-preference"
Observations:
- "{pattern description} | confidence:{high|medium|low} | source:{correction|explicit|inferred} | date:{YYYY-MM-DD}"
```

**Categories:**
- `naming` — variable/function/file naming conventions
- `structure` — code organization, file layout, module boundaries
- `error-handling` — try/catch style, error types, recovery patterns
- `testing` — test style, coverage expectations, framework preferences
- `styling` — CSS approach, component styling, design tokens
- `api` — endpoint design, request/response format, auth patterns
- `git` — commit style, branch naming, PR conventions
- `tooling` — preferred tools, build config, linter settings
- `communication` — how they like to interact (terse, detailed, etc.)

---

## Velocity Tracking

Track these metrics per session (store in memory MCP under "vibe-velocity"):

| Metric | What | Why |
|--------|------|-----|
| Tasks completed | Count of distinct tasks done | Raw throughput |
| Correction rate | Corrections / total outputs | Quality signal |
| Iteration depth | Avg iterations per task | Efficiency signal |
| Flow breaks | Times user had to re-explain | Communication quality |
| Time-to-first-output | How fast first draft ships | Responsiveness |

**Velocity formula:** `velocity_score = tasks_completed * (1 - correction_rate) * (1 / avg_iteration_depth)`

Higher score = better vibe coding session.

---

## Self-Training Triggers

### Automatic Triggers (no user action needed)
1. **Correction detected** → micro-loop activates
2. **Same correction 3x** → promote to persistent pattern
3. **Session ending** → meso-loop reflection
4. **New session start** → macro-loop context load
5. **3+ failed fix attempts** → capture debugging lesson

### Manual Triggers (user can invoke)
- "remember this pattern" → immediately capture to memory + vibe-patterns
- "forget that preference" → remove from memory + vibe-patterns
- "show my patterns" → display current vibe-patterns.md
- "reset preferences" → clear vibe-patterns (fresh start)
- "how am I doing?" → show velocity metrics

---

## Integration Points

### Memory MCP
- **Read** at session start (macro-loop)
- **Write** at session end (meso-loop) and on significant learnings
- **Search** when encountering familiar patterns

### Context Keeper MCP
- **Read** for project state
- **Update** when project context changes

### Learned Heuristics
- **Append** when debugging lessons emerge (3+ failed attempts)
- **Read** to avoid repeating past mistakes

### vibe-patterns.md
- **Read** at session start
- **Update** when new persistent patterns discovered
- **Prune** when patterns become stale (not seen in 10+ sessions)

---

## Anti-Patterns (What NOT to Do)

1. **Don't announce learning** — "I noticed you prefer X" is annoying. Just do X.
2. **Don't over-generalize** — One correction in React doesn't mean they want the same in Python.
3. **Don't be sycophantic** — Learning from the user ≠ agreeing with everything.
4. **Don't slow down to learn** — Learning happens in the background, not at the cost of speed.
5. **Don't store sensitive data** — Never capture passwords, API keys, or PII in patterns.
6. **Don't fight the user** — If they want something different from their usual pattern, do it. Preferences evolve.
7. **Don't create analysis paralysis** — When in doubt, ship the simpler version and iterate.

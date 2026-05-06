# Learned Heuristics
> Auto-maintained by AI. Lessons learned from debugging sessions are appended here.
> Each entry follows: `- [YYYY-MM-DD] {context}: {lesson learned}`

## Heuristics

- (none yet — entries will be added automatically after 3+ failed fix attempts)

## Advisory & Analysis Quality

- [2026-05-04] Codebase audit severity rating: NEVER mark an issue "critical" without verifying the code path is actually exercised in the real production flow. Trace from endpoint → handler → the specific code. If the code path is dead or only used in an alternate flow, downgrade severity.
- [2026-05-04] Verify before claiming a bug exists: Read the CURRENT code, not assumptions from earlier versions. The pre-flight probe was already removed but was still recommended for removal — wasted user trust.
- [2026-05-04] "Theoretically possible" ≠ "actually happens": When auditing (e.g., SSE parser strictness), check what the upstream ACTUALLY sends before claiming data loss. Theoretical spec violations that never occur in practice are defensive fixes, not critical bugs.
- [2026-05-04] Consider existing client capabilities before recommending proxy features: If the client (e.g., OpenCode) already has system prompts, context compression, and model selection, don't recommend redundant proxy-level features as "high priority". Acknowledge overlap explicitly.
- [2026-05-04] Don't recommend fragile implementations: Regex-based fact extraction from AI responses is unreliable. If an implementation approach is inherently brittle, flag it as experimental/risky rather than presenting it as a solid solution.
- [2026-05-04] Self-review severity and claims BEFORE delivering to user: Do a final pass asking "is this actually true in the real flow?" for every finding. Don't wait for the user to ask "is any of this overclaimed?" — that damages credibility.

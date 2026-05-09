/**
 * Auto-Review Plugin
 * 
 * Quality gate that triggers after significant task completion.
 * Injects a review reminder into the agent's context when:
 * 1. A task() delegation completes (tool.execute.after on task tool)
 * 2. Multiple file writes happen in sequence (batch edit detection)
 * 3. Session goes idle after significant work
 * 
 * Does NOT auto-run review — it surfaces a reminder/nudge to the agent
 * to self-review before reporting completion to the user.
 */

const CONFIG = {
  // Minimum file edits before triggering review nudge
  editThreshold: 3,
  // Minimum tool calls before triggering review nudge  
  toolThreshold: 8,
  // Cooldown between review nudges (ms)
  nudgeCooldownMs: 120_000, // 2 minutes
  // Tools that count as "significant work"
  significantTools: ['write', 'edit', 'bash', 'lsp_rename', 'ast_grep_replace'],
  // Tools that indicate task delegation completed
  delegationTools: ['task'],
  // Don't nudge for these agents (they ARE the reviewers)
  excludeAgents: ['oracle', 'momus', 'reviewer'],
};

export default async (input, options) => {
  // Per-session tracking
  const sessions = new Map();

  function getSession(sessionId) {
    if (!sessions.has(sessionId)) {
      sessions.set(sessionId, {
        editCount: 0,
        toolCount: 0,
        filesChanged: new Set(),
        lastNudgeAt: 0,
        delegationsCompleted: 0,
        significantWorkDone: false,
      });
    }
    return sessions.get(sessionId);
  }

  function shouldNudge(state) {
    const now = Date.now();
    if (now - state.lastNudgeAt < CONFIG.nudgeCooldownMs) return false;
    
    // Trigger conditions (any one is enough)
    if (state.delegationsCompleted > 0) return true;
    if (state.editCount >= CONFIG.editThreshold) return true;
    if (state.toolCount >= CONFIG.toolThreshold && state.significantWorkDone) return true;
    
    return false;
  }

  function buildNudge(state) {
    const files = [...state.filesChanged].slice(0, 10);
    const parts = [];
    
    parts.push(`[AUTO-REVIEW REMINDER]`);
    parts.push(`Significant work detected: ${state.editCount} edits across ${state.filesChanged.size} file(s).`);
    
    if (state.delegationsCompleted > 0) {
      parts.push(`${state.delegationsCompleted} delegated task(s) completed.`);
    }
    
    parts.push('');
    parts.push('Before reporting completion to the user, verify:');
    parts.push('1. Run lsp_diagnostics on changed files — are there new errors?');
    parts.push('2. Do the changes match the original request?');
    parts.push('3. Are there any edge cases or error paths not handled?');
    parts.push('4. If tests exist, have they been run?');
    
    if (files.length > 0) {
      parts.push('');
      parts.push(`Changed files: ${files.join(', ')}`);
    }

    return parts.join('\n');
  }

  function resetSession(sessionId) {
    const state = getSession(sessionId);
    state.editCount = 0;
    state.toolCount = 0;
    state.filesChanged.clear();
    state.delegationsCompleted = 0;
    state.significantWorkDone = false;
    state.lastNudgeAt = Date.now();
  }

  return {
    // Track tool executions to detect significant work
    'tool.execute.after': async (data) => {
      const { tool, sessionID, result, args } = data || {};
      if (!sessionID || !tool) return;

      const state = getSession(sessionID);

      // Track significant tools
      const toolName = typeof tool === 'string' ? tool : tool?.name;
      if (!toolName) return;

      if (CONFIG.significantTools.includes(toolName)) {
        state.significantWorkDone = true;
        state.toolCount++;

        // Track file edits
        if (['write', 'edit'].includes(toolName) && args?.filePath) {
          state.editCount++;
          state.filesChanged.add(args.filePath);
        }
        if (toolName === 'ast_grep_replace' && !args?.dryRun) {
          state.editCount++;
        }
      }

      // Track delegation completions
      if (CONFIG.delegationTools.includes(toolName)) {
        state.delegationsCompleted++;
      }
    },

    // Inject review nudge into chat when conditions are met
    'experimental.chat.system': async (data) => {
      const { sessionID, agent } = data || {};
      if (!sessionID) return;

      // Don't nudge review agents
      const agentId = typeof agent === 'string' ? agent : agent?.id || agent?.name;
      if (agentId && CONFIG.excludeAgents.includes(agentId)) return;

      const state = getSession(sessionID);
      
      if (shouldNudge(state)) {
        const nudge = buildNudge(state);
        resetSession(sessionID);
        return { append: nudge };
      }
    },

    // Clean up on session end
    event: async (event) => {
      if (!event?.properties) return;
      const { type, sessionID } = event.properties;
      
      if (type === 'session.deleted' && sessionID) {
        sessions.delete(sessionID);
      }
    }
  };
};

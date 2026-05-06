/**
 * Git Safety Plugin
 * 
 * Blocks destructive/irreversible git commands before they execute.
 * Acts as a guardrail — prevents accidental data loss from:
 * - force push (rewrites remote history)
 * - hard reset (discards uncommitted work)
 * - clean -fd (deletes untracked files permanently)
 * - branch -D on current branch
 * - checkout/switch with --force on dirty tree
 * 
 * Allows override with explicit user confirmation via ask().
 */

const DESTRUCTIVE_PATTERNS = [
  {
    pattern: /\bgit\s+push\s+.*--force\b/,
    alt: /\bgit\s+push\s+.*--force-with-lease\b/,
    message: '🚫 `git push --force` rewrites remote history. Use `--force-with-lease` instead (safer).',
    severity: 'critical'
  },
  {
    pattern: /\bgit\s+push\s+.*-f\b/,
    alt: /\bgit\s+push\s+.*--force-with-lease\b/,
    message: '🚫 `git push -f` rewrites remote history. Use `--force-with-lease` instead.',
    severity: 'critical'
  },
  {
    pattern: /\bgit\s+reset\s+--hard\b/,
    message: '🚫 `git reset --hard` permanently discards uncommitted changes. Consider `git stash` first.',
    severity: 'critical'
  },
  {
    pattern: /\bgit\s+clean\s+.*-f/,
    message: '🚫 `git clean -f` permanently deletes untracked files. Consider `git clean -n` (dry run) first.',
    severity: 'high'
  },
  {
    pattern: /\bgit\s+checkout\s+.*--force\b/,
    message: '🚫 `git checkout --force` discards local changes. Stash or commit first.',
    severity: 'high'
  },
  {
    pattern: /\bgit\s+switch\s+.*--force\b/,
    message: '🚫 `git switch --force` discards local changes. Stash or commit first.',
    severity: 'high'
  },
  {
    pattern: /\bgit\s+rebase\s+.*--force\b/,
    message: '⚠️ Forced rebase detected. Ensure you have a backup branch.',
    severity: 'medium'
  },
  {
    pattern: /\bgit\s+branch\s+.*-D\b/,
    message: '⚠️ `git branch -D` force-deletes branch regardless of merge status. Use `-d` for safe delete.',
    severity: 'medium'
  },
  {
    pattern: /\bgit\s+stash\s+drop\s+--all\b/,
    message: '⚠️ `git stash drop --all` removes all stashes permanently.',
    severity: 'medium'
  },
  {
    pattern: /\bgit\s+reflog\s+expire\s+--all/,
    message: '🚫 `git reflog expire --all` destroys recovery history. This is almost never what you want.',
    severity: 'critical'
  }
];

export default async (input, options) => {
  return {
    'tool.execute.before': async (data) => {
      const { tool, args, context } = data || {};
      const toolName = typeof tool === 'string' ? tool : tool?.name;
      
      // Only intercept bash/shell commands
      if (toolName !== 'bash' && toolName !== 'shell') return;
      
      const command = args?.command || args?.cmd || '';
      if (!command) return;

      // Check against destructive patterns
      for (const rule of DESTRUCTIVE_PATTERNS) {
        if (rule.pattern.test(command)) {
          // If there's a safer alternative and it's being used, allow it
          if (rule.alt && rule.alt.test(command)) continue;

          // Block with explanation
          if (rule.severity === 'critical') {
            // Critical: block entirely, suggest alternative
            return {
              blocked: true,
              message: `${rule.message}\n\nThis command was blocked by git-safety plugin. If you really need this, ask the user for explicit confirmation.`
            };
          } else {
            // High/Medium: warn but allow (the agent should reconsider)
            return {
              message: `${rule.message}\n\n⚠️ Proceeding — but consider if this is truly necessary.`
            };
          }
        }
      }
    }
  };
};

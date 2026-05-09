/**
 * Wisdom Keeper Plugin
 * 
 * Structured wisdom management system for OpenCode.
 * Stores learnings as categorized, scoped, searchable JSONL entries.
 * 
 * Storage: ~/.sisyphus/wisdom/
 *   - system.jsonl    → cross-project wisdom
 *   - project-<hash>.jsonl → project-specific wisdom
 *   - plan-<hash>.jsonl   → plan-specific wisdom
 * 
 * Categories: gotcha, pattern, fact, decision, warning, preference
 * Scopes: system, project, plan
 * 
 * Provides 4 tools: wisdom_write, wisdom_search, wisdom_recall, wisdom_gc
 */

import { readFileSync, writeFileSync, appendFileSync, existsSync, readdirSync, statSync, mkdirSync } from 'fs';
import { join, basename } from 'path';
import { createHash } from 'crypto';

const WISDOM_DIR = join(process.env.HOME || '/tmp', '.sisyphus', 'wisdom');
const MAX_ENTRIES_PER_FILE = 500;
const STALE_DAYS = 90;

// Categories with descriptions
const CATEGORIES = {
  gotcha: 'Surprising behavior, footgun, or non-obvious trap',
  pattern: 'Reusable solution pattern that works well',
  fact: 'Verified technical fact or constraint',
  decision: 'Architecture or design decision with rationale',
  warning: 'Something to avoid — causes problems',
  preference: 'User preference or style choice'
};

// Scopes
const SCOPES = ['system', 'project', 'plan'];

function hashString(str) {
  return createHash('md5').update(str).digest('hex').slice(0, 12);
}

function getFilePath(scope, projectPath) {
  if (scope === 'system') return join(WISDOM_DIR, 'system.jsonl');
  if (scope === 'project') return join(WISDOM_DIR, `project-${hashString(projectPath || 'unknown')}.jsonl`);
  if (scope === 'plan') return join(WISDOM_DIR, `plan-${hashString(projectPath || 'unknown')}.jsonl`);
  return join(WISDOM_DIR, 'system.jsonl');
}

function readEntries(filePath) {
  if (!existsSync(filePath)) return [];
  const content = readFileSync(filePath, 'utf-8').trim();
  if (!content) return [];
  return content.split('\n').map(line => {
    try { return JSON.parse(line); }
    catch { return null; }
  }).filter(Boolean);
}

function writeEntries(filePath, entries) {
  writeFileSync(filePath, entries.map(e => JSON.stringify(e)).join('\n') + '\n');
}

function appendEntry(filePath, entry) {
  appendFileSync(filePath, JSON.stringify(entry) + '\n');
}

function searchEntries(query, scope, projectPath, category) {
  const files = [];
  
  if (scope === 'system' || !scope) {
    files.push(getFilePath('system'));
  }
  if ((scope === 'project' || !scope) && projectPath) {
    files.push(getFilePath('project', projectPath));
  }
  if ((scope === 'plan' || !scope) && projectPath) {
    files.push(getFilePath('plan', projectPath));
  }
  // If no scope specified, search all files
  if (!scope && !projectPath) {
    try {
      const allFiles = readdirSync(WISDOM_DIR).filter(f => f.endsWith('.jsonl'));
      files.push(...allFiles.map(f => join(WISDOM_DIR, f)));
    } catch {}
  }

  const queryLower = query.toLowerCase();
  const results = [];

  for (const file of files) {
    const entries = readEntries(file);
    for (const entry of entries) {
      if (category && entry.category !== category) continue;
      
      const searchable = [
        entry.content,
        entry.title || '',
        entry.context || '',
        ...(entry.tags || [])
      ].join(' ').toLowerCase();

      if (searchable.includes(queryLower)) {
        results.push({ ...entry, _file: basename(file) });
      }
    }
  }

  // Sort by relevance (exact title match first, then recency)
  results.sort((a, b) => {
    const aTitle = (a.title || '').toLowerCase().includes(queryLower) ? 1 : 0;
    const bTitle = (b.title || '').toLowerCase().includes(queryLower) ? 1 : 0;
    if (aTitle !== bTitle) return bTitle - aTitle;
    return new Date(b.timestamp) - new Date(a.timestamp);
  });

  return results.slice(0, 20);
}

function dedup(entry, filePath) {
  const entries = readEntries(filePath);
  // Check for near-duplicate (same category + similar content)
  const contentLower = entry.content.toLowerCase();
  for (const existing of entries) {
    if (existing.category === entry.category) {
      const existingLower = existing.content.toLowerCase();
      // Simple similarity: if >80% of words overlap, it's a dupe
      const entryWords = new Set(contentLower.split(/\s+/));
      const existingWords = new Set(existingLower.split(/\s+/));
      const intersection = [...entryWords].filter(w => existingWords.has(w));
      const similarity = intersection.length / Math.max(entryWords.size, existingWords.size);
      if (similarity > 0.8) return true;
    }
  }
  return false;
}

function gcEntries(filePath) {
  const entries = readEntries(filePath);
  const now = Date.now();
  const staleMs = STALE_DAYS * 24 * 60 * 60 * 1000;
  
  const kept = entries.filter(entry => {
    // Never GC decisions or facts — they're permanent
    if (entry.category === 'decision' || entry.category === 'fact') return true;
    // GC stale entries that haven't been accessed
    const age = now - new Date(entry.timestamp).getTime();
    if (age > staleMs && (!entry.lastAccessed || now - new Date(entry.lastAccessed).getTime() > staleMs)) {
      return false;
    }
    return true;
  });

  const removed = entries.length - kept.length;
  if (removed > 0) writeEntries(filePath, kept);
  return removed;
}

// Secret detection — never store API keys, passwords, tokens
function containsSecret(text) {
  const patterns = [
    /(?:api[_-]?key|apikey|secret|password|passwd|token|auth)[=:]\s*['"]?[a-zA-Z0-9_\-]{20,}/i,
    /(?:sk|pk|rk|ak)-[a-zA-Z0-9]{20,}/,
    /ghp_[a-zA-Z0-9]{36}/,
    /eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+/,
    /-----BEGIN (?:RSA |EC )?PRIVATE KEY-----/,
  ];
  return patterns.some(p => p.test(text));
}

// Lazy-load Zod from OpenCode's runtime (exposed via @opencode-ai/plugin or globalThis)
let _z = null;
function z() {
  if (_z) return _z;
  // Try multiple ways to get Zod
  try {
    // OpenCode exposes zod via the plugin SDK
    const zod = await import('zod');
    _z = zod.z || zod.default || zod;
    return _z;
  } catch {}
  // Fallback: try zod/v4
  try {
    const zod = await import('zod/v4');
    _z = zod.z || zod.default || zod;
    return _z;
  } catch {}
  return null;
}

export default async (input, options) => {
  // Ensure wisdom directory exists
  try {
    mkdirSync(WISDOM_DIR, { recursive: true });
  } catch {}

  // Get Zod for schema definitions — required by OpenCode v1.14+
  let zod;
  try {
    const zodMod = await import('zod');
    zod = zodMod.z || zodMod.default || zodMod;
  } catch {
    try {
      const zodMod = await import('zod/v4');
      zod = zodMod.z || zodMod.default || zodMod;
    } catch {
      // Final fallback: construct a minimal Zod-like interface
      // This shouldn't happen since OpenCode bundles Zod
      console.warn('[wisdom-keeper] Could not load Zod, tools may not register correctly');
    }
  }

  // Helper: create string schema with description
  const str = (desc) => zod ? zod.string().describe(desc) : { type: 'string', description: desc };
  const optStr = (desc) => zod ? zod.string().optional().describe(desc) : { type: 'string', description: desc };

  return {
    tool: {
      // TOOL 1: Write wisdom
      wisdom_write: {
        description: `Store a wisdom entry. Categories: ${Object.entries(CATEGORIES).map(([k,v]) => `${k} (${v})`).join(', ')}. Scopes: system (cross-project), project (this project), plan (current plan). Use this to capture learnings, gotchas, patterns, decisions, and preferences.`,
        args: {
          title: optStr('Short title (max 80 chars)'),
          content: str('The wisdom content — what was learned'),
          category: str('One of: gotcha, pattern, fact, decision, warning, preference'),
          scope: optStr('One of: system, project, plan. Default: system'),
          context: optStr('Optional: what triggered this learning'),
          tags: optStr('Optional: comma-separated tags for searchability')
        },
        async execute(args, ctx) {
          const { title, content, category, context, tags } = args;
          const scope = args.scope || 'system';

          // Validate
          if (!content) return 'Error: content is required';
          if (!category || !CATEGORIES[category]) {
            return `Error: category must be one of: ${Object.keys(CATEGORIES).join(', ')}`;
          }
          if (!SCOPES.includes(scope)) {
            return `Error: scope must be one of: ${SCOPES.join(', ')}`;
          }

          // Secret detection
          if (containsSecret(content) || containsSecret(title || '') || containsSecret(context || '')) {
            return 'Error: content appears to contain secrets (API keys, tokens, passwords). Wisdom entries must not contain sensitive data.';
          }

          const projectPath = ctx?.directory || ctx?.worktree || '';
          const filePath = getFilePath(scope, projectPath);

          const entry = {
            id: hashString(`${Date.now()}-${Math.random()}`),
            title: (title || '').slice(0, 80),
            content,
            category,
            scope,
            context: context || null,
            tags: tags ? tags.split(',').map(t => t.trim()).filter(Boolean) : [],
            timestamp: new Date().toISOString(),
            lastAccessed: null,
            sessionId: ctx?.sessionID || null
          };

          // Dedup check
          if (dedup(entry, filePath)) {
            return 'Skipped: near-duplicate entry already exists.';
          }

          // Size guard
          const existing = readEntries(filePath);
          if (existing.length >= MAX_ENTRIES_PER_FILE) {
            // Auto-GC before adding
            gcEntries(filePath);
          }

          appendEntry(filePath, entry);
          return `Wisdom stored: [${category}/${scope}] "${title || content.slice(0, 40)}..." (${basename(filePath)})`;
        }
      },

      // TOOL 2: Search wisdom
      wisdom_search: {
        description: 'Search stored wisdom entries by keyword, category, or scope. Returns matching entries sorted by relevance.',
        args: {
          query: str('Search query — matches against title, content, context, and tags'),
          category: optStr('Optional: filter by category (gotcha/pattern/fact/decision/warning/preference)'),
          scope: optStr('Optional: filter by scope (system/project/plan)')
        },
        async execute(args, ctx) {
          const { query, category, scope } = args;
          if (!query) return 'Error: query is required';

          const projectPath = ctx?.directory || ctx?.worktree || '';
          const results = searchEntries(query, scope, projectPath, category);

          if (results.length === 0) return 'No wisdom entries found matching query.';

          // Mark as accessed
          for (const r of results) {
            r.lastAccessed = new Date().toISOString();
          }

          const formatted = results.map((r, i) => 
            `${i + 1}. [${r.category}] ${r.title || r.content.slice(0, 50)}\n   ${r.content}\n   ${r.tags?.length ? `Tags: ${r.tags.join(', ')}` : ''} | ${r.timestamp.slice(0, 10)} | ${r._file}`
          ).join('\n\n');

          return `Found ${results.length} entries:\n\n${formatted}`;
        }
      },

      // TOOL 3: Recall wisdom (proactive — for session start)
      wisdom_recall: {
        description: 'Recall all relevant wisdom for the current project/context. Use at session start to load accumulated knowledge. Returns recent and high-value entries.',
        args: {
          limit: optStr('Max entries to return (default: 15)')
        },
        async execute(args, ctx) {
          const limit = parseInt(args.limit) || 15;
          const projectPath = ctx?.directory || ctx?.worktree || '';
          
          const allEntries = [];
          
          // Load system wisdom
          const systemEntries = readEntries(getFilePath('system'));
          allEntries.push(...systemEntries.map(e => ({ ...e, _scope: 'system' })));
          
          // Load project wisdom
          if (projectPath) {
            const projectEntries = readEntries(getFilePath('project', projectPath));
            allEntries.push(...projectEntries.map(e => ({ ...e, _scope: 'project' })));
          }

          if (allEntries.length === 0) return 'No wisdom entries yet. Start capturing learnings with wisdom_write.';

          // Priority: warnings > gotchas > decisions > patterns > facts > preferences
          const priority = { warning: 6, gotcha: 5, decision: 4, pattern: 3, fact: 2, preference: 1 };
          
          allEntries.sort((a, b) => {
            const pDiff = (priority[b.category] || 0) - (priority[a.category] || 0);
            if (pDiff !== 0) return pDiff;
            return new Date(b.timestamp) - new Date(a.timestamp);
          });

          const top = allEntries.slice(0, limit);
          const formatted = top.map((e, i) =>
            `${i + 1}. [${e.category}/${e._scope}] ${e.title || e.content.slice(0, 50)}\n   ${e.content}${e.context ? `\n   Context: ${e.context}` : ''}`
          ).join('\n\n');

          return `Wisdom recall (${top.length}/${allEntries.length} entries):\n\n${formatted}`;
        }
      },

      // TOOL 4: Garbage collect
      wisdom_gc: {
        description: 'Garbage collect stale wisdom entries. Removes entries older than 90 days that haven\'t been accessed. Decisions and facts are never removed.',
        args: {},
        async execute(args, ctx) {
          let totalRemoved = 0;
          try {
            const files = readdirSync(WISDOM_DIR).filter(f => f.endsWith('.jsonl'));
            for (const file of files) {
              totalRemoved += gcEntries(join(WISDOM_DIR, file));
            }
          } catch (err) {
            return `Error during GC: ${err.message}`;
          }
          return totalRemoved > 0 
            ? `GC complete: removed ${totalRemoved} stale entries.`
            : 'GC complete: no stale entries found.';
        }
      }
    },

    // Hook: Auto-capture wisdom from session events
    event: async (event) => {
      // Could hook into session.idle to prompt wisdom capture
      // For now, wisdom capture is tool-driven (agent calls wisdom_write)
    }
  };
};

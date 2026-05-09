/**
 * auto-checkpoint — Background git commits on idle
 *
 * Creates automatic git checkpoints when the AI stops working for a configurable
 * period. Safety net so you never lose work.
 *
 * Config (via plugin options in opencode.json):
 *   idleMs:           ms of no tool activity before checkpoint (default: 15000)
 *   quietMs:          additional quiet period after idle detected (default: 5000)
 *   cooldownMs:       min ms between checkpoints (default: 30000)
 *   includeUntracked: stage untracked files too (default: true)
 *   logFile:          path to log file (default: ~/.config/opencode/auto-checkpoint.log)
 */

import { execSync, spawn } from "node:child_process";
import { appendFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const DEFAULT_CONFIG = {
  idleMs: 15000,
  quietMs: 5000,
  cooldownMs: 30000,
  includeUntracked: true,
  logFile: join(homedir(), ".config", "opencode", "auto-checkpoint.log"),
};

// Simple mutex — serialize git operations per worktree
class Mutex {
  #queue = [];
  #locked = false;

  async acquire() {
    if (!this.#locked) {
      this.#locked = true;
      return;
    }
    return new Promise((resolve) => this.#queue.push(resolve));
  }

  release() {
    if (this.#queue.length > 0) {
      const next = this.#queue.shift();
      next();
    } else {
      this.#locked = false;
    }
  }
}

// Per-worktree mutexes
const mutexes = new Map();
function getMutex(cwd) {
  if (!mutexes.has(cwd)) mutexes.set(cwd, new Mutex());
  return mutexes.get(cwd);
}

// Session state tracking
const sessions = new Map();

function log(cfg, msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  try {
    appendFileSync(cfg.logFile, line);
  } catch {
    // silent — log file not critical
  }
}

function git(args, cwd) {
  try {
    return execSync(`git ${args}`, {
      cwd,
      encoding: "utf-8",
      timeout: 10000,
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
  } catch {
    return null;
  }
}

function isGitRepo(cwd) {
  return git("rev-parse --is-inside-work-tree", cwd) === "true";
}

function isGitBusy(cwd) {
  const gitDir = git("rev-parse --git-dir", cwd);
  if (!gitDir) return true;
  const base = gitDir.startsWith("/") ? gitDir : join(cwd, gitDir);
  return (
    existsSync(join(base, "rebase-merge")) ||
    existsSync(join(base, "rebase-apply")) ||
    existsSync(join(base, "MERGE_HEAD")) ||
    existsSync(join(base, "CHERRY_PICK_HEAD"))
  );
}

function hasDirtyTree(cwd, includeUntracked) {
  const staged = git("diff --cached --quiet", cwd);
  const unstaged = git("diff --quiet", cwd);
  // diff --quiet exits 1 if there are changes, execSync throws
  // so we check differently
  try {
    execSync("git diff --cached --quiet", { cwd, stdio: "pipe" });
    execSync("git diff --quiet", { cwd, stdio: "pipe" });
    if (includeUntracked) {
      const untracked = execSync("git ls-files --others --exclude-standard", {
        cwd,
        encoding: "utf-8",
        stdio: ["pipe", "pipe", "pipe"],
      }).trim();
      return untracked.length > 0;
    }
    return false;
  } catch {
    return true; // diff --quiet exits 1 = there are changes
  }
}

function getCurrentSha(cwd) {
  return git("rev-parse HEAD", cwd);
}

function hasActiveChildren(sessionId) {
  const state = sessions.get(sessionId);
  if (!state || !state.childIds) return false;
  for (const childId of state.childIds) {
    if (sessions.has(childId)) return true;
  }
  return false;
}

async function doCheckpoint(cfg, state) {
  const { cwd, sessionId } = state;
  const mutex = getMutex(cwd);

  await mutex.acquire();
  try {
    // Safety checks
    if (!isGitRepo(cwd)) return;
    if (isGitBusy(cwd)) {
      log(cfg, `[${sessionId}] skip: git operation in progress`);
      return;
    }
    if (hasActiveChildren(sessionId)) {
      log(cfg, `[${sessionId}] skip: active child sessions`);
      return;
    }
    if (!hasDirtyTree(cwd, cfg.includeUntracked)) {
      log(cfg, `[${sessionId}] skip: clean tree`);
      return;
    }

    // Cooldown check
    const now = Date.now();
    if (state.lastCommitAt && now - state.lastCommitAt < cfg.cooldownMs) {
      log(cfg, `[${sessionId}] skip: cooldown (${cfg.cooldownMs}ms)`);
      return;
    }

    // SHA dedup — don't commit if HEAD hasn't changed since last checkpoint
    const currentSha = getCurrentSha(cwd);
    if (currentSha && currentSha === state.lastCommitSha) {
      log(cfg, `[${sessionId}] skip: SHA unchanged`);
      return;
    }

    // Stage changes
    if (cfg.includeUntracked) {
      git("add -A", cwd);
    } else {
      git("add -u", cwd);
    }

    // Build commit message
    const timestamp = new Date().toISOString();
    const shortSession = sessionId ? sessionId.slice(0, 8) : "unknown";
    const msg = `checkpoint(auto): work in progress [session=${shortSession}] [${timestamp}]`;

    // Commit
    const result = git(`commit -m "${msg}" --no-verify`, cwd);
    if (result !== null) {
      state.lastCommitAt = now;
      state.lastCommitSha = getCurrentSha(cwd);
      log(cfg, `[${sessionId}] checkpoint created: ${msg}`);
    } else {
      log(cfg, `[${sessionId}] commit failed or nothing to commit`);
    }
  } finally {
    mutex.release();
  }
}

function scheduleCheckpoint(cfg, state) {
  // Clear existing timer
  if (state.timer) {
    clearTimeout(state.timer);
    state.timer = null;
  }

  const delay = cfg.idleMs + cfg.quietMs;
  state.timer = setTimeout(() => {
    doCheckpoint(cfg, state).catch((err) => {
      log(cfg, `[${state.sessionId}] error: ${err.message}`);
    });
  }, delay);
}

function resetIdleTimer(cfg, state) {
  state.lastToolAt = Date.now();
  scheduleCheckpoint(cfg, state);
}

// Plugin entry point
const plugin = async (input, options) => {
  const cfg = { ...DEFAULT_CONFIG, ...options };

  log(cfg, "auto-checkpoint plugin loaded");

  return {
    event: (event) => {
      const { type, properties } = event;

      if (type === "session.created" || type === "session.idle") {
        const sessionId =
          properties?.sessionId || properties?.session_id || "unknown";
        const cwd = properties?.cwd || properties?.directory || process.cwd();

        if (!sessions.has(sessionId)) {
          sessions.set(sessionId, {
            sessionId,
            cwd,
            parentId: properties?.parentId || null,
            childIds: new Set(),
            lastToolAt: Date.now(),
            lastIdleAt: null,
            lastCommitAt: null,
            lastCommitSha: null,
            timer: null,
          });

          // Register as child of parent
          if (properties?.parentId && sessions.has(properties.parentId)) {
            sessions.get(properties.parentId).childIds.add(sessionId);
          }
        }

        if (type === "session.idle") {
          const state = sessions.get(sessionId);
          if (state) {
            state.lastIdleAt = Date.now();
            scheduleCheckpoint(cfg, state);
          }
        }
      }

      if (type === "session.deleted") {
        const sessionId =
          properties?.sessionId || properties?.session_id || "unknown";
        const state = sessions.get(sessionId);
        if (state) {
          // Final checkpoint before session dies
          doCheckpoint(cfg, state).catch(() => {});

          if (state.timer) clearTimeout(state.timer);

          // Remove from parent's children
          if (state.parentId && sessions.has(state.parentId)) {
            sessions.get(state.parentId).childIds.delete(sessionId);
          }

          sessions.delete(sessionId);
        }
      }

      if (type === "session.status") {
        const sessionId =
          properties?.sessionId || properties?.session_id || "unknown";
        const state = sessions.get(sessionId);
        if (state && properties?.status === "idle") {
          state.lastIdleAt = Date.now();
          scheduleCheckpoint(cfg, state);
        }
      }
    },

    "tool.execute.after": (result) => {
      // Track tool activity — reset idle timer
      const sessionId = result?.context?.sessionID || result?.sessionId;
      if (!sessionId) return result;

      const state = sessions.get(sessionId);
      if (state) {
        resetIdleTimer(cfg, state);
      }

      // Track child sessions from task() calls
      if (
        result?.context?.metadata &&
        typeof result.context.metadata === "function"
      ) {
        try {
          const meta = result.context.metadata();
          if (meta?.session_id && meta?.background_task_id) {
            // This was a task() call — register child
            state?.childIds?.add(meta.session_id);
          }
        } catch {
          // metadata() might not be available
        }
      }

      return result;
    },
  };
};

export default plugin;

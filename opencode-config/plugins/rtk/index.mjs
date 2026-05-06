/**
 * opencode-rtk-local — RTK (Rust Token Killer) integration
 *
 * Intercepts bash/shell tool calls and rewrites supported commands
 * to use RTK for token-optimized output. Reduces context consumption
 * by 60-90% on common dev commands (git, ls, cat, test, etc).
 *
 * Requires: rtk binary in PATH (brew install rtk)
 */

import { execSync } from "node:child_process";

const RTK_COMMANDS = new Map([
  ["git", "rtk git"],
  ["gh", "rtk gh"],
  ["ls", "rtk ls"],
  ["tree", "rtk tree"],
  ["cat", "rtk read"],
  ["rg", "rtk grep"],
  ["grep", "rtk grep"],
  ["cargo test", "rtk test"],
  ["cargo build", "rtk cargo build"],
  ["cargo clippy", "rtk cargo clippy"],
  ["npm test", "rtk test"],
  ["pnpm test", "rtk test"],
  ["pytest", "rtk test"],
  ["docker ps", "rtk docker ps"],
  ["docker compose", "rtk docker compose"],
  ["kubectl get", "rtk kubectl get"],
  ["kubectl describe", "rtk kubectl describe"],
  ["kubectl logs", "rtk kubectl logs"],
  ["curl", "rtk curl"],
]);

const SKIP_PATTERNS = [
  /^cd\s/,
  /^echo\s/,
  /^export\s/,
  /^source\s/,
  /^mkdir\s/,
  /^rm\s/,
  /^mv\s/,
  /^cp\s/,
  /^chmod\s/,
  /^chown\s/,
  /^pip install/,
  /^npm install/,
  /^brew install/,
  /^cargo install/,
  /&&/,
  /\|/,
  /;/,
  />/,
  /</,
];

let rtkAvailable = null;

function checkRtk() {
  if (rtkAvailable !== null) return rtkAvailable;
  try {
    execSync("rtk --version", { stdio: "pipe" });
    rtkAvailable = true;
  } catch {
    rtkAvailable = false;
  }
  return rtkAvailable;
}

function shouldSkip(command) {
  return SKIP_PATTERNS.some((p) => p.test(command));
}

function rewriteCommand(command) {
  if (!checkRtk()) return command;
  if (shouldSkip(command)) return command;

  const trimmed = command.trim();

  for (const [prefix, replacement] of RTK_COMMANDS) {
    if (trimmed === prefix || trimmed.startsWith(prefix + " ")) {
      const args = trimmed.slice(prefix.length);
      return replacement + args;
    }
  }

  return command;
}

export default function plugin(api) {
  api.hook("tool.execute.before", (ctx) => {
    if (ctx.tool !== "bash" && ctx.tool !== "shell") return ctx;
    if (!ctx.params?.command) return ctx;

    const original = ctx.params.command;
    const rewritten = rewriteCommand(original);

    if (rewritten !== original) {
      ctx.params.command = rewritten;
    }

    return ctx;
  });
}

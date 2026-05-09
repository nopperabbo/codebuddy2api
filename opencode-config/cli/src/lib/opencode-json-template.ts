/**
 * Default opencode.json template for fresh installs.
 * Contains all MCP servers and plugin config that should be active out-of-the-box.
 *
 * Format: OpenCode native (NOT Claude Desktop format).
 * - MCP: { "type", "command"/"url", "env", "enabled" }
 * - LSP: auto-detected from installed commands at install time.
 */

import { join } from "path";
import { existsSync, readFileSync } from "fs";
import { execFileSync } from "child_process";
import { platform } from "os";

// ─── LSP Auto-Detection ──────────────────────────────────────

const FILETYPE_EXTENSIONS: Record<string, string[]> = {
  python: [".py", ".pyi"],
  typescript: [".ts", ".tsx"],
  javascript: [".js", ".jsx", ".mjs", ".cjs"],
  typescriptreact: [".tsx"],
  javascriptreact: [".jsx"],
  rust: [".rs"],
  go: [".go"],
  dockerfile: [".dockerfile"],
  sql: [".sql"],
  java: [".java"],
  c: [".c", ".h"],
  cpp: [".cpp", ".cc", ".cxx", ".hpp", ".hh"],
  objc: [".m", ".mm"],
  php: [".php"],
  ruby: [".rb"],
  bash: [".sh", ".bash"],
  sh: [".sh"],
  yaml: [".yaml", ".yml"],
  html: [".html", ".htm"],
  css: [".css"],
  scss: [".scss"],
  kotlin: [".kt", ".kts"],
  dart: [".dart"],
  lua: [".lua"],
  svelte: [".svelte"],
  vue: [".vue"],
  terraform: [".tf", ".tfvars"],
  tf: [".tf"],
  zig: [".zig"],
  markdown: [".md"],
  toml: [".toml"],
  graphql: [".graphql", ".gql"],
  gql: [".graphql", ".gql"],
  elixir: [".ex", ".exs"],
  eelixir: [".eex", ".heex"],
  scala: [".scala", ".sbt"],
  csharp: [".cs"],
  json: [".json", ".jsonc"],
  zsh: [".zsh"],
  yml: [".yaml", ".yml"],
  less: [".less"],
  hcl: [".hcl"],
  htm: [".html"],
  sbt: [".sbt"],
  jsonc: [".jsonc"],
};

function commandExists(cmd: string): boolean {
  if (!/^[\w@./+:-]+$/.test(cmd)) return false;

  try {
    const checkCmd = platform() === "win32" ? "where" : "which";
    execFileSync(checkCmd, [cmd], { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

interface LspEntry {
  command: string[];
  extensions: string[];
}

/**
 * Scan lsp.json and return LSP servers whose commands are found in PATH.
 */
export function detectInstalledLsp(configDir: string): Record<string, LspEntry> {
  const lspFile = join(configDir, "lsp.json");
  if (!existsSync(lspFile)) return {};

  let lspData: { lsp: Record<string, { command: string; args: string[]; filetypes: string[] }> };
  try {
    lspData = JSON.parse(readFileSync(lspFile, "utf8"));
  } catch {
    return {};
  }

  const result: Record<string, LspEntry> = {};

  for (const [name, entry] of Object.entries(lspData.lsp || {})) {
    if (!commandExists(entry.command)) continue;

    const extensions: string[] = [];
    for (const ft of entry.filetypes) {
      const exts = FILETYPE_EXTENSIONS[ft];
      if (exts) {
        for (const ext of exts) {
          if (!extensions.includes(ext)) extensions.push(ext);
        }
      }
    }
    if (extensions.length === 0) continue;

    result[name] = {
      command: [entry.command, ...entry.args],
      extensions,
    };
  }

  return result;
}

// ─── Template Builder ────────────────────────────────────────

export function buildDefaultMcpConfig(configDir: string): Record<string, unknown> {
  const contextKeeperPath = join(configDir, "cli", "src", "mcp", "context-keeper.ts")
    .replace(/\\/g, "/");

  return {
    "context-keeper": {
      type: "local",
      command: ["bun", "run", contextKeeperPath],
      env: {
        PROJECT_ROOT: "${PROJECT_ROOT}",
      },
      enabled: true,
    },
    "context7": {
      type: "remote",
      url: "https://mcp.context7.com/mcp",
      enabled: true,
    },
    "github-search": {
      type: "local",
      command: ["npx", "-y", "@modelcontextprotocol/server-github"],
      env: {
        GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}",
      },
      enabled: true,
    },
    "filesystem": {
      type: "local",
      command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "./"],
      enabled: true,
    },
    "memory": {
      type: "local",
      command: ["npx", "-y", "@modelcontextprotocol/server-memory"],
      enabled: true,
    },
    "playwright": {
      type: "local",
      command: ["npx", "-y", "@playwright/mcp@0.0.28"],
      enabled: true,
    },
    "sequential-thinking": {
      type: "local",
      command: ["npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
      enabled: true,
    },
    "postgres": {
      type: "local",
      command: ["npx", "-y", "@modelcontextprotocol/server-postgres"],
      env: {
        POSTGRES_CONNECTION_STRING: "${DATABASE_URL}",
      },
      enabled: false,
    },
  };
}

/**
 * Build the default opencode.json content.
 * @param configDir - The resolved config directory (e.g., ~/.config/opencode)
 *                    Used to compute the context-keeper path and detect LSP.
 */
export function buildDefaultOpenCodeJson(configDir: string): Record<string, unknown> {
  // Auto-detect installed LSP servers
  const lsp = detectInstalledLsp(configDir);

  return {
    $schema: "https://opencode.ai/config.json",
    plugin: [
      "superpowers@git+https://github.com/obra/superpowers.git",
    ],
    mcp: buildDefaultMcpConfig(configDir),
    lsp,
  };
}

import { join, dirname } from "path";
import { homedir, platform } from "os";
import { existsSync } from "fs";
import { readFile, writeFile, mkdir } from "fs/promises";

/**
 * Returns the cross-platform config directory for OpenCode JCE.
 * - All platforms: $XDG_CONFIG_HOME/opencode or ~/.config/opencode
 */
/**
 * Auto-detect the OpenCode config directory.
 * Searches for existing config (opencode.json as marker) in candidate paths.
 * Falls back to ~/.config/opencode/ (OpenCode standard on all platforms).
 */
export function getConfigDir(): string {
  const candidates: string[] = [];

  // 1. XDG_CONFIG_HOME (if set)
  const xdgConfig = process.env.XDG_CONFIG_HOME;
  if (xdgConfig) {
    candidates.push(join(xdgConfig, "opencode"));
  }

  // 2. ~/.config/opencode (OpenCode standard on all platforms)
  candidates.push(join(homedir(), ".config", "opencode"));

  // Search for existing config (opencode.json is the marker)
  for (const path of candidates) {
    if (existsSync(join(path, "opencode.json"))) {
      return path;
    }
  }

  // Default: ~/.config/opencode/
  return candidates[0] || join(homedir(), ".config", "opencode");
}

/**
 * Returns the legacy config directory (%APPDATA%\opencode on Windows).
 * Used for migration purposes only.
 */
export function getLegacyConfigDir(): string {
  if (platform() === "win32" && process.env.APPDATA) {
    return join(process.env.APPDATA, "opencode");
  }
  return getConfigDir();
}

/**
 * Check if a config file exists at the given path relative to config dir.
 */
export function configFileExists(relativePath: string): boolean {
  const fullPath = join(getConfigDir(), relativePath);
  return existsSync(fullPath);
}

/**
 * Load and parse a JSON config file from the config directory.
 * Returns the parsed object or throws with a user-friendly message.
 */
export async function loadConfigFile<T>(relativePath: string): Promise<T> {
  const fullPath = join(getConfigDir(), relativePath);

  if (!existsSync(fullPath)) {
    throw new Error(`Config file not found: ${fullPath}`);
  }

  const content = await readFile(fullPath, "utf-8");

  try {
    return JSON.parse(content) as T;
  } catch {
    throw new Error(`Invalid JSON in: ${fullPath}`);
  }
}

/**
 * Get the full path to a config file.
 */
export function getConfigPath(relativePath: string): string {
  return join(getConfigDir(), relativePath);
}

/**
 * Get the path to OpenCode's own opencode.json config file.
 * Uses the same directory as getConfigDir() for consistency.
 */
export function getOpenCodeConfigPath(): string {
  return join(getConfigDir(), "opencode.json");
}

/**
 * Load OpenCode's opencode.json config.
 * If the file does not exist, creates it with the full default template
 * (MCP servers, plugin, LSP auto-detect) so that subsequent writes
 * never produce a partial config.
 */
export async function loadOpenCodeConfig(): Promise<Record<string, any>> {
  const configPath = getOpenCodeConfigPath();

  try {
    let content = await readFile(configPath, "utf-8");
    // Strip UTF-8 BOM if present (Windows editors add this)
    if (content.charCodeAt(0) === 0xFEFF) {
      content = content.slice(1);
    }
    return JSON.parse(content) ?? {};
  } catch (err: any) {
    if (err.code === "ENOENT") {
      // Auto-create with full template
      const { buildDefaultOpenCodeJson } = await import("./opencode-json-template.js");
      const configDir = getConfigDir();
      const template = buildDefaultOpenCodeJson(configDir);
      await mkdir(dirname(configPath), { recursive: true });
      await writeFile(configPath, JSON.stringify(template, null, 2) + "\n", "utf-8");
      return template as Record<string, any>;
    }
    throw new Error(`Invalid JSON in OpenCode config: ${configPath}`);
  }
}

/**
 * Save OpenCode's opencode.json config (preserving existing keys).
 */
export async function saveOpenCodeConfig(config: Record<string, any>): Promise<void> {
  const configPath = getOpenCodeConfigPath();
  await mkdir(dirname(configPath), { recursive: true });
  await writeFile(configPath, JSON.stringify(config, null, 2) + "\n", "utf-8");
}

// ─── LSP Config Mapping ─────────────────────────────────────

/**
 * OpenCode LSP format:
 * {
 *   "lsp": {
 *     "server-name": {
 *       "command": ["cmd", "--args"],
 *       "extensions": [".ts", ".js"]
 *     }
 *   }
 * }
 */

interface LspServerDef {
  command: string[];
  extensions: string[];
}

/** Map of filetype names to file extensions */
const FILETYPE_TO_EXTENSIONS: Record<string, string[]> = {
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
  zsh: [".zsh"],
  yaml: [".yaml", ".yml"],
  yml: [".yaml", ".yml"],
  html: [".html", ".htm"],
  htm: [".html"],
  css: [".css"],
  scss: [".scss"],
  less: [".less"],
  kotlin: [".kt", ".kts"],
  dart: [".dart"],
  lua: [".lua"],
  svelte: [".svelte"],
  vue: [".vue"],
  terraform: [".tf", ".tfvars"],
  tf: [".tf"],
  hcl: [".hcl"],
  zig: [".zig"],
  markdown: [".md"],
  toml: [".toml"],
  graphql: [".graphql", ".gql"],
  gql: [".graphql", ".gql"],
  elixir: [".ex", ".exs"],
  eelixir: [".eex", ".heex"],
  scala: [".scala", ".sbt"],
  sbt: [".sbt"],
  csharp: [".cs"],
  json: [".json", ".jsonc"],
  jsonc: [".jsonc"],
};

/**
 * Convert our lsp.json format to OpenCode's opencode.json lsp format.
 * Only includes servers whose command is found in PATH.
 */
export function buildOpenCodeLspConfig(
  lspJson: { lsp: Record<string, { server: string; command: string; args: string[]; filetypes: string[] }> },
  installedCommands: string[]
): Record<string, LspServerDef> {
  const result: Record<string, LspServerDef> = {};

  for (const [name, entry] of Object.entries(lspJson.lsp)) {
    // Only include if the command is installed
    if (!installedCommands.includes(entry.command)) continue;

    // Build extensions list from filetypes
    const extensions: string[] = [];
    for (const ft of entry.filetypes) {
      const exts = FILETYPE_TO_EXTENSIONS[ft];
      if (exts) {
        for (const ext of exts) {
          if (!extensions.includes(ext)) extensions.push(ext);
        }
      }
    }

    // Skip servers with no recognized extensions
    if (extensions.length === 0) continue;

    // Build command array
    const command = [entry.command, ...entry.args];

    result[name] = { command, extensions };
  }

  return result;
}

/**
 * Merge LSP servers into OpenCode's opencode.json.
 * Only adds new servers — does not overwrite existing ones.
 * Returns the list of servers that were added.
 */
export async function mergeLspToOpenCodeConfig(
  lspServers: Record<string, LspServerDef>
): Promise<{ added: string[]; skipped: string[] }> {
  const config = await loadOpenCodeConfig();

  if (!config.lsp) {
    config.lsp = {};
  }

  const added: string[] = [];
  const skipped: string[] = [];

  for (const [name, def] of Object.entries(lspServers)) {
    if (config.lsp[name]) {
      skipped.push(name);
    } else {
      config.lsp[name] = def;
      added.push(name);
    }
  }

  if (added.length > 0) {
    await saveOpenCodeConfig(config);
  }

  return { added, skipped };
}

import { Command } from "commander";
import { existsSync, readdirSync } from "fs";
import { dirname, join, sep } from "path";
import { cp, mkdir, writeFile, readFile, chmod, rename } from "fs/promises";
import { platform } from "os";
import chalk from "chalk";
import { getConfigDir } from "../lib/config.js";
import { banner, heading, info, success, warn, error } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import {
  initVersionFile,
  runMigrations,
  compareVersions,
} from "../lib/version.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";
import { GITHUB_RAW_BASE, GITHUB_REPO, VERSION } from "../lib/constants.js";

// ─── Types ───────────────────────────────────────────────────

interface RemotePackageJson {
  version: string;
}

interface GitHubContentEntry {
  name: string;
  type: string;
  path: string;
}

interface MergeStats {
  agents: number;
  mcpServers: number;
  lspEntries: number;
  profiles: number;
  prompts: number;
  skills: number;
  agentsMdUpdated: boolean;
  fallbackSkipped: boolean;
  fetchFailed: number;
  fetchAttempted: number;
}

// ─── GitHub Fetch Helpers ────────────────────────────────────

/**
 * Fetch the latest version from GitHub.
 */
async function fetchLatestVersion(): Promise<string | null> {
  try {
    const response = await fetch(`${GITHUB_RAW_BASE}/package.json`, {
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) {
      return null;
    }
    const data = (await response.json()) as RemotePackageJson;
    return data.version || null;
  } catch {
    return null;
  }
}

/**
 * Fetch a raw file from the config directory on GitHub.
 */
async function fetchRemoteFile(relativePath: string): Promise<string | null> {
  try {
    const url = `${GITHUB_RAW_BASE}/config/${relativePath}`;
    const response = await fetch(url, {
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) {
      return null;
    }
    return await response.text();
  } catch {
    return null;
  }
}

/**
 * Fetch the list of files in a directory from the GitHub repository.
 * Returns an array of filenames.
 */
async function fetchDirectoryListing(dir: string): Promise<string[]> {
  try {
    const response = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/contents/config/${dir}`,
      {
        headers: { Accept: "application/vnd.github.v3+json" },
        signal: AbortSignal.timeout(15000),
      }
    );
    if (!response.ok) {
      return [];
    }
    const files = (await response.json()) as GitHubContentEntry[];
    return files
      .filter((f) => f.type === "file")
      .map((f) => f.name);
  } catch {
    return [];
  }
}

// ─── Self-Update CLI ─────────────────────────────────────────

/**
 * Update the opencode-jce CLI itself to the latest version.
 * 1. Clones the latest source from GitHub into ~/.config/opencode/cli/
 * 2. Ensures the .cmd shim points to the updated local CLI folder
 * 3. Removes any .exe that bun may have created (which would take precedence over .cmd)
 * Returns true if the CLI was updated successfully.
 */
async function selfUpdateCli(latestVersion: string): Promise<boolean> {
  if (VERSION === latestVersion) {
    info("Syncing CLI to latest build...");
  } else {
    info(`Updating CLI: ${VERSION} → ${latestVersion}...`);
  }

  try {
    await updateLocalCliFolder();
    await ensureCliShim();
    success(`CLI updated to v${latestVersion}.`);
    return true;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    warn(`CLI self-update failed: ${msg}`);
    warn("Try running the installer again to fix.");
    return false;
  }
}

/**
 * Update the local cli/ folder in the config directory.
 * Clones the latest source from GitHub, copies src/, schemas/, package.json,
 * tsconfig.json, and installs dependencies.
 * Throws on failure so selfUpdateCli can report it.
 */
async function updateLocalCliFolder(): Promise<void> {
  const configDir = getConfigDir();
  const cliDir = join(configDir, "cli");

  info("Downloading latest CLI source...");

  // Clone to temp, copy relevant files
  const tempDir = join(configDir, ".cli-update-tmp");
  const { rm } = await import("fs/promises");

  // Clean up any previous temp
  if (existsSync(tempDir)) {
    await rm(tempDir, { recursive: true, force: true });
  }

  // Clone latest
  const cloneProc = Bun.spawn(
    ["git", "clone", "--depth", "1", `https://github.com/${GITHUB_REPO}.git`, tempDir],
    { stdout: "pipe", stderr: "pipe" }
  );
  const cloneExit = await cloneProc.exited;
  if (cloneExit !== 0) {
    throw new Error("Could not clone repo from GitHub.");
  }

  const stagingDir = join(configDir, ".cli-update-new");
  const backupDir = join(configDir, ".cli-update-backup");
  for (const dir of [stagingDir, backupDir]) {
    if (existsSync(dir)) {
      await rm(dir, { recursive: true, force: true });
    }
  }
  await mkdir(stagingDir, { recursive: true });

  // Copy new files into staging first. The active CLI is not touched until
  // dependencies are installed and all required source files are present.
  await cp(join(tempDir, "src"), join(stagingDir, "src"), { recursive: true });
  await cp(join(tempDir, "schemas"), join(stagingDir, "schemas"), { recursive: true });
  if (existsSync(join(tempDir, "scripts"))) {
    await cp(join(tempDir, "scripts"), join(stagingDir, "scripts"), { recursive: true });
  }

  for (const file of ["package.json", "tsconfig.json", "bun.lock"]) {
    const src = join(tempDir, file);
    if (existsSync(src)) {
      const content = await readFile(src, "utf-8");
      await writeTextFile(join(stagingDir, file), content);
    }
  }

  if (!existsSync(join(stagingDir, "src", "index.ts"))) {
    throw new Error("Downloaded CLI source is missing src/index.ts.");
  }

  // Install dependencies
  const installProc = Bun.spawn(
    ["bun", "install"],
    { stdout: "pipe", stderr: "pipe", cwd: stagingDir }
  );
  const installExit = await installProc.exited;
  if (installExit !== 0) {
    const stderr = await new Response(installProc.stderr).text();
    throw new Error(`bun install failed while updating CLI dependencies.${stderr ? ` ${stderr}` : ""}`);
  }

  try {
    if (existsSync(cliDir)) {
      await rename(cliDir, backupDir);
    }
    await rename(stagingDir, cliDir);
    if (existsSync(backupDir)) {
      await rm(backupDir, { recursive: true, force: true });
    }
  } catch (err) {
    if (!existsSync(cliDir) && existsSync(backupDir)) {
      await rename(backupDir, cliDir);
    }
    throw err;
  }

  // Cleanup temp
  await rm(tempDir, { recursive: true, force: true });

  success("CLI source updated.");
}

/**
 * Ensure the CLI shim (.cmd) is correct and remove any .exe that would
 * take precedence on Windows. The .exe is created by `bun install -g` but
 * points to stale code in bun's global cache instead of our local cli/ folder.
 */
export async function ensureCliShim(): Promise<void> {
  const configDir = getConfigDir();
  const cliDir = join(configDir, "cli");
  const bunBinDir = join(process.env.USERPROFILE || process.env.HOME || "", ".bun", "bin");

  if (!existsSync(bunBinDir)) {
    await mkdir(bunBinDir, { recursive: true });
  }

  const { rm } = await import("fs/promises");
  const isWindows = platform() === "win32";
  const staleFiles = isWindows
    ? ["opencode-jce", "opencode-jce.exe", "opencode-jce.bunx"]
    : ["opencode-jce.cmd", "opencode-jce.exe", "opencode-jce.bunx"];

  for (const file of staleFiles) {
    const filePath = join(bunBinDir, file);
    if (existsSync(filePath)) {
      await rm(filePath, { force: true });
    }
  }

  if (isWindows) {
    const cmdPath = join(bunBinDir, "opencode-jce.cmd");
    const cmdContent = `@echo off\r\nbun run "${join(cliDir, "src", "index.ts")}" %*`;
    await writeFile(cmdPath, cmdContent, "ascii");
  } else {
    const shimPath = join(bunBinDir, "opencode-jce");
    const shimContent = `#!/usr/bin/env sh\nexec bun run "${join(cliDir, "src", "index.ts")}" "$@"\n`;
    await writeFile(shimPath, shimContent, "utf-8");
    await chmod(shimPath, 0o755);
  }

  info("CLI shim updated.");
}

// ─── Local File Helpers ──────────────────────────────────────

/**
 * Read and parse a local JSON file. Returns null if it doesn't exist or can't be parsed.
 */
async function readLocalJson<T>(filePath: string): Promise<T | null> {
  if (!existsSync(filePath)) {
    return null;
  }
  try {
    const content = await readFile(filePath, "utf-8");
    return JSON.parse(content) as T;
  } catch {
    return null;
  }
}

/**
 * Write a JSON object to a file with pretty formatting.
 */
async function writeJson(filePath: string, data: unknown): Promise<void> {
  const dir = dirname(filePath);
  if (!existsSync(dir)) {
    await mkdir(dir, { recursive: true });
  }
  await writeFile(filePath, JSON.stringify(data, null, 2) + "\n", "utf-8");
}

/**
 * Write a string to a file, creating parent directories if needed.
 */
async function writeTextFile(filePath: string, content: string): Promise<void> {
  const dir = dirname(filePath);
  if (!existsSync(dir)) {
    await mkdir(dir, { recursive: true });
  }
  await writeFile(filePath, content, "utf-8");
}

// ─── Merge Logic ─────────────────────────────────────────────

/**
 * Merge agents.json: add new agents by ID, skip existing ones.
 * Returns the number of new agents added.
 */
async function mergeAgents(configDir: string): Promise<number> {
  const localPath = join(configDir, "agents.json");
  const remoteContent = await fetchRemoteFile("agents.json");
  if (!remoteContent) return -1;

  let remoteData: { agents: Array<{ id: string; [key: string]: unknown }> };
  try {
    remoteData = JSON.parse(remoteContent);
  } catch {
    return 0;
  }

  if (!remoteData.agents || !Array.isArray(remoteData.agents)) return 0;

  const localData = await readLocalJson<{ agents: Array<{ id: string; [key: string]: unknown }> }>(localPath);
  const localAgents = localData?.agents ?? [];
  const localIds = new Set(localAgents.map((a) => a.id));

  const newAgents = remoteData.agents.filter((a) => !localIds.has(a.id));
  if (newAgents.length === 0 && localAgents.length > 0) return 0;

  const mergedAgents = [...localAgents, ...newAgents];
  await writeJson(localPath, { agents: mergedAgents });
  return newAgents.length;
}

/**
 * Merge mcp.json: add new MCP servers by key, skip existing ones.
 * Returns the number of new servers added.
 */
async function mergeMcpServers(configDir: string): Promise<number> {
  const localPath = join(configDir, "mcp.json");
  const remoteContent = await fetchRemoteFile("mcp.json");
  if (!remoteContent) return -1;

  let remoteData: { mcpServers: Record<string, unknown> };
  try {
    remoteData = JSON.parse(remoteContent);
  } catch {
    return 0;
  }

  if (!remoteData.mcpServers || typeof remoteData.mcpServers !== "object") return 0;

  const localData = await readLocalJson<{ mcpServers: Record<string, unknown> }>(localPath);
  const localServers = localData?.mcpServers ?? {};

  let addedCount = 0;
  const merged = { ...localServers };

  for (const [key, value] of Object.entries(remoteData.mcpServers)) {
    if (!(key in merged)) {
      merged[key] = value;
      addedCount++;
    }
  }

  if (addedCount === 0 && Object.keys(localServers).length > 0) return 0;

  await writeJson(localPath, { mcpServers: merged });
  return addedCount;
}

/**
 * Merge lsp.json: add new LSP entries by key, skip existing ones.
 * Returns the number of new entries added.
 */
async function mergeLspEntries(configDir: string): Promise<number> {
  const localPath = join(configDir, "lsp.json");
  const remoteContent = await fetchRemoteFile("lsp.json");
  if (!remoteContent) return -1;

  let remoteData: { lsp: Record<string, unknown> };
  try {
    remoteData = JSON.parse(remoteContent);
  } catch {
    return 0;
  }

  if (!remoteData.lsp || typeof remoteData.lsp !== "object") return 0;

  const localData = await readLocalJson<{ lsp: Record<string, unknown> }>(localPath);
  const localLsp = localData?.lsp ?? {};

  let addedCount = 0;
  const merged = { ...localLsp };

  for (const [key, value] of Object.entries(remoteData.lsp)) {
    if (!(key in merged)) {
      merged[key] = value;
      addedCount++;
    }
  }

  if (addedCount === 0 && Object.keys(localLsp).length > 0) return 0;

  await writeJson(localPath, { lsp: merged });
  return addedCount;
}

/**
 * Merge a directory: copy new files only, skip existing filenames.
 * Returns the number of new files added.
 */
async function mergeDirectory(configDir: string, dirName: string): Promise<number> {
  const localDir = join(configDir, dirName);
  const remoteFiles = await fetchDirectoryListing(dirName);
  if (remoteFiles.length === 0) {
    // Distinguish "nothing new" from "fetch failed"
    if (!existsSync(localDir) || readdirSync(localDir).length === 0) {
      return -1; // Likely fetch failure — local dir is empty/missing
    }
    return 0;
  }

  if (!existsSync(localDir)) {
    await mkdir(localDir, { recursive: true });
  }

  let addedCount = 0;

  for (const fileName of remoteFiles) {
    const localPath = join(localDir, fileName);
    if (existsSync(localPath)) {
      continue; // Skip existing files
    }

    const content = await fetchRemoteFile(`${dirName}/${fileName}`);
    if (content) {
      await writeTextFile(localPath, content);
      addedCount++;
    }
  }

  return addedCount;
}

/**
 * Handle AGENTS.md: always overwrite (system instruction must be latest).
 * Returns true if updated.
 */
async function updateAgentsMd(configDir: string): Promise<boolean> {
  const content = await fetchRemoteFile("AGENTS.md");
  if (!content) return false;

  const localPath = join(configDir, "AGENTS.md");

  // Preserve user edits: backup before overwriting
  if (existsSync(localPath)) {
    const localContent = await readFile(localPath, "utf-8");
    if (localContent !== content) {
      const backupPath = join(configDir, "AGENTS.md.backup");
      await writeTextFile(backupPath, localContent);
      info("  AGENTS.md changed — backup saved to AGENTS.md.backup");
    }
  }

  await writeTextFile(localPath, content);
  return true;
}

/**
 * Handle fallback.json: skip if already exists (user may have customized).
 * Returns true if the file was written (i.e., it didn't exist before).
 */
async function handleFallback(configDir: string): Promise<boolean> {
  const localPath = join(configDir, "fallback.json");
  if (existsSync(localPath)) {
    return false; // Skip — user may have customized
  }

  const content = await fetchRemoteFile("fallback.json");
  if (!content) return false;

  await writeTextFile(localPath, content);
  return true;
}

/**
 * Ensure OpenCode's primary config exists before migrations register MCP/LSP.
 */
async function ensureOpenCodeJson(configDir: string): Promise<boolean> {
  const localPath = join(configDir, "opencode.json");
  const { buildDefaultMcpConfig, buildDefaultOpenCodeJson } = await import("../lib/opencode-json-template.js");
  if (!existsSync(localPath)) {
    await writeJson(localPath, buildDefaultOpenCodeJson(configDir));
    return true;
  }

  const existing = await readLocalJson<Record<string, any>>(localPath);
  if (!existing) return false;

  if (!existing.mcp || typeof existing.mcp !== "object") {
    existing.mcp = {};
  }

  let changed = false;
  for (const [key, value] of Object.entries(buildDefaultMcpConfig(configDir))) {
    if (!(key in existing.mcp)) {
      existing.mcp[key] = value;
      changed = true;
    }
  }

  // Repair context-keeper if it exists but is missing required env.PROJECT_ROOT
  if (existing.mcp["context-keeper"] && (!existing.mcp["context-keeper"].env || !existing.mcp["context-keeper"].env.PROJECT_ROOT)) {
    const defaults = buildDefaultMcpConfig(configDir);
    existing.mcp["context-keeper"] = defaults["context-keeper"];
    changed = true;
  }

  if (changed) {
    await writeJson(localPath, existing);
  }
  return changed;
}

// ─── Main Merge Orchestrator ─────────────────────────────────

/**
 * Perform a merge-based update: fetch remote configs and merge them
 * with local configs, preserving user customizations.
 */
async function mergeUpdatedConfigs(): Promise<MergeStats> {
  const configDir = getConfigDir();

  // Ensure config directory exists
  if (!existsSync(configDir)) {
    await mkdir(configDir, { recursive: true });
  }

  const stats: MergeStats = {
    agents: 0,
    mcpServers: 0,
    lspEntries: 0,
    profiles: 0,
    prompts: 0,
    skills: 0,
    agentsMdUpdated: false,
    fallbackSkipped: false,
    fetchFailed: 0,
    fetchAttempted: 0,
  };

  // 1. Merge JSON config files
  info("Ensuring opencode.json...");
  await ensureOpenCodeJson(configDir);

  info("Merging agents.json...");
  stats.fetchAttempted++;
  stats.agents = await mergeAgents(configDir);
  if (stats.agents < 0) { stats.fetchFailed++; stats.agents = 0; }

  info("Merging mcp.json...");
  stats.fetchAttempted++;
  stats.mcpServers = await mergeMcpServers(configDir);
  if (stats.mcpServers < 0) { stats.fetchFailed++; stats.mcpServers = 0; }

  info("Merging lsp.json...");
  stats.fetchAttempted++;
  stats.lspEntries = await mergeLspEntries(configDir);
  if (stats.lspEntries < 0) { stats.fetchFailed++; stats.lspEntries = 0; }

  // 2. Merge directories (only add new files)
  info("Merging profiles/...");
  stats.fetchAttempted++;
  stats.profiles = await mergeDirectory(configDir, "profiles");
  if (stats.profiles < 0) { stats.fetchFailed++; stats.profiles = 0; }

  info("Merging prompts/...");
  stats.fetchAttempted++;
  stats.prompts = await mergeDirectory(configDir, "prompts");
  if (stats.prompts < 0) { stats.fetchFailed++; stats.prompts = 0; }

  info("Merging skills/...");
  stats.fetchAttempted++;
  stats.skills = await mergeDirectory(configDir, "skills");
  if (stats.skills < 0) { stats.fetchFailed++; stats.skills = 0; }

  // 3. AGENTS.md — overwrite only if remote is newer, preserve user edits otherwise
  info("Updating AGENTS.md...");
  stats.fetchAttempted++;
  stats.agentsMdUpdated = await updateAgentsMd(configDir);
  if (!stats.agentsMdUpdated && !existsSync(join(configDir, "AGENTS.md"))) { stats.fetchFailed++; }

  // 4. fallback.json — skip if exists
  info("Checking fallback.json...");
  const fallbackWritten = await handleFallback(configDir);
  stats.fallbackSkipped = !fallbackWritten && existsSync(join(configDir, "fallback.json"));

  return stats;
}

// ─── Report ──────────────────────────────────────────────────

/**
 * Print a human-readable summary of what was merged.
 */
function printMergeReport(stats: MergeStats): void {
  console.log();
  heading("Merge Summary");

  const items: string[] = [];

  if (stats.agents > 0) items.push(`${stats.agents} agent(s)`);
  if (stats.mcpServers > 0) items.push(`${stats.mcpServers} MCP server(s)`);
  if (stats.lspEntries > 0) items.push(`${stats.lspEntries} LSP entry/entries`);
  if (stats.profiles > 0) items.push(`${stats.profiles} profile(s)`);
  if (stats.prompts > 0) items.push(`${stats.prompts} prompt(s)`);
  if (stats.skills > 0) items.push(`${stats.skills} skill(s)`);

  if (items.length > 0) {
    success(`Added: ${items.join(", ")}`);
  } else {
    info("No new items to add — your config already has everything.");
  }

  if (stats.agentsMdUpdated) {
    success("AGENTS.md updated to latest version.");
  }

  if (stats.fallbackSkipped) {
    info("fallback.json skipped (local copy preserved).");
  }
}

// ─── Command ─────────────────────────────────────────────────

export const updateCommand = new Command("update")
  .description("Update CLI and merge latest configuration from GitHub")
  .option("--check", "Only check for updates without applying them")
  .option("--force", "Force sync even when local version is newer than remote")
  .action(async (options: { check?: boolean; force?: boolean }) => {
    logCommandStart("update", options);
    banner();
    heading("Update Check");

    // Ensure version file exists
    await initVersionFile();

    // Use the actual binary version (VERSION) as the authoritative local version.
    // version.json tracks config schema, but the binary version is what determines
    // whether the CLI itself needs updating.
    const localVersion = VERSION;

    info(`Current local version: ${chalk.bold(localVersion)}`);

    // Fetch latest version from GitHub
    info("Checking for updates...");
    const latestVersion = await fetchLatestVersion();

    if (!latestVersion) {
      error("Could not reach GitHub to check for updates.");
      error("Check your internet connection and try again.");
      logCommandError("update", "Failed to fetch latest version from GitHub");
      process.exit(EXIT_ERROR);
    }

    info(`Latest remote version: ${chalk.bold(latestVersion)}`);
    console.log();

    const comparison = compareVersions(latestVersion, localVersion);

    if (comparison > 0) {
      info(`${chalk.yellow("Update available:")} ${localVersion} → ${latestVersion}`);
    } else if (comparison < 0) {
      warn(`Local version (${localVersion}) is newer than remote (${latestVersion}).`);
      if (!options.force) {
        info("Skipping self-update to avoid downgrading. Use --force only if you intentionally want to sync remote main.");
      }
    } else {
      info("Version is current. Syncing latest files...");
    }

    // Check-only mode
    if (options.check) {
      if (comparison > 0) {
        info("Run `opencode-jce update` to apply the update.");
      } else if (comparison < 0) {
        info("No update applied because local version is newer than remote.");
      } else {
        info("Run `opencode-jce update` to sync latest files.");
      }
      logCommandSuccess("update", `check complete, latest=${latestVersion}`);
      process.exit(EXIT_SUCCESS);
    }

    if (comparison < 0 && !options.force) {
      logCommandSuccess("update", `skipped downgrade, local=${localVersion}, remote=${latestVersion}`);
      process.exit(EXIT_SUCCESS);
    }

    // Step 1: Self-update CLI
    console.log();
    heading("Step 1: Update CLI");
    const cliUpdated = await selfUpdateCli(latestVersion);
    if (!cliUpdated) {
      logCommandError("update", "CLI self-update failed");
      process.exit(EXIT_ERROR);
    }

    // Step 2: Merge config files
    console.log();
    heading("Step 2: Merge Configuration");

    // Backup current config
    const configDir = getConfigDir();
    if (existsSync(configDir)) {
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const backupDir = `${configDir}.update-backup.${timestamp}`;
      info(`Backing up current config to: ${backupDir}`);
      try {
        await cp(configDir, backupDir, {
          recursive: true,
          filter: (src) => !src.includes(`${sep}cli${sep}`) && !src.endsWith(`${sep}cli`),
        });
        success("Backup created.");
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        warn(`Backup failed: ${msg} — continuing anyway.`);
      }
    }

    // Merge remote configs into local
    info("Downloading and merging latest configuration...");
    const stats = await mergeUpdatedConfigs();

    // Check if anything was actually fetched
    const totalChanges =
      stats.agents +
      stats.mcpServers +
      stats.lspEntries +
      stats.profiles +
      stats.prompts +
      stats.skills +
      (stats.agentsMdUpdated ? 1 : 0);

    if (totalChanges === 0 && stats.fetchFailed > 0) {
      warn(`${stats.fetchFailed}/${stats.fetchAttempted} fetch(es) failed. Update may have failed.`);
      warn("Check your internet connection or try again later.");
      logCommandError("update", `${stats.fetchFailed} fetches failed during merge`);
      process.exit(EXIT_ERROR);
    }

    // Print merge report
    printMergeReport(stats);

    // Run migrations based on version.json state (independent of binary version)
    console.log();
    info("Running migrations...");
    const migrationsRun = await runMigrations(latestVersion);
    if (migrationsRun > 0) {
      success(`Ran ${migrationsRun} migration(s).`);
    } else {
      info("No migrations needed.");
    }

    // Final summary
    console.log();
    heading("Update Complete");
    if (comparison > 0) {
      success(`Version: ${localVersion} → ${latestVersion}`);
    } else {
      success(`Synced to latest build (v${latestVersion}).`);
    }
    info("Your existing customizations have been preserved.");
    info("Run `opencode-jce doctor` to verify your installation.");

    logCommandSuccess("update", `synced to ${latestVersion}, added ${totalChanges} item(s)`);
    process.exit(EXIT_SUCCESS);
  });

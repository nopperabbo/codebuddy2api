import { join, resolve, sep } from "path";
import { existsSync } from "fs";
import { readFile, writeFile, mkdir } from "fs/promises";
import { getConfigDir } from "./config.js";
import { sanitizeGitUrl } from "./plugins.js";

export interface TeamConfig {
  repoUrl: string;
  lastSync: string;
  branch: string;
}

const TEAM_CONFIG_FILE = "team.json";

/**
 * Get the path to the team config file.
 */
export function getTeamConfigPath(): string {
  return join(getConfigDir(), TEAM_CONFIG_FILE);
}

/**
 * Load team config. Returns null if not initialized.
 */
export async function loadTeamConfig(): Promise<TeamConfig | null> {
  const configPath = getTeamConfigPath();

  if (!existsSync(configPath)) {
    return null;
  }

  const content = await readFile(configPath, "utf-8");
  try {
    return JSON.parse(content) as TeamConfig;
  } catch {
    throw new Error(`Failed to parse team config: invalid JSON in ${configPath}`);
  }
}

/**
 * Save team config.
 */
export async function saveTeamConfig(config: TeamConfig): Promise<void> {
  const configPath = getTeamConfigPath();
  const configDir = getConfigDir();

  if (!existsSync(configDir)) {
    await mkdir(configDir, { recursive: true });
  }

  await writeFile(configPath, JSON.stringify(config, null, 2) + "\n", "utf-8");
}

/**
 * Initialize team sync with a Git repository URL.
 */
export async function initTeamSync(
  repoUrl: string,
  branch: string = "main"
): Promise<{ success: boolean; error?: string }> {
  try {
    // Validate URL format
    try {
      const parsed = new URL(repoUrl);
      if (parsed.protocol !== "https:" && parsed.protocol !== "git:") {
        return { success: false, error: "Repository URL must use https: or git: protocol" };
      }
    } catch {
      return { success: false, error: "Invalid repository URL format" };
    }

    const config: TeamConfig = {
      repoUrl: sanitizeGitUrl(repoUrl),
      lastSync: new Date().toISOString(),
      branch,
    };

    await saveTeamConfig(config);
    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
}

/**
 * Push current config to the team repository.
 */
export async function pushTeamConfig(): Promise<{ success: boolean; error?: string }> {
  const teamConfig = await loadTeamConfig();

  if (!teamConfig) {
    return { success: false, error: "Team sync not initialized. Run: opencode-jce team init <git-url>" };
  }

  // Validate repo URL and branch
  try {
    const parsed = new URL(teamConfig.repoUrl);
    if (parsed.protocol !== "https:" && parsed.protocol !== "git:") {
      return { success: false, error: "Team repo URL must use https: or git: protocol" };
    }
  } catch {
    return { success: false, error: "Team repo URL is not a valid URL" };
  }
  if (!/^[a-zA-Z0-9._\/-]+$/.test(teamConfig.branch)) {
    return { success: false, error: "Team branch name contains invalid characters" };
  }
  if (teamConfig.branch.includes("..")) {
    return { success: false, error: "Branch name must not contain '..' sequences" };
  }

  const configDir = getConfigDir();
  const tempDir = join(configDir, ".team-sync");

  try {
    // Always remove stale .team-sync before clone
    if (existsSync(tempDir)) {
      await cleanup(tempDir);
    }

    // Clone the team repo
    const proc = Bun.spawn(["git", "clone", "--depth", "1", "--branch", teamConfig.branch, teamConfig.repoUrl, tempDir], {
      stdout: "pipe",
      stderr: "pipe",
    });
    await proc.exited;

    if (proc.exitCode !== 0) {
      const stderr = await new Response(proc.stderr).text();
      return { success: false, error: `Failed to clone team repo: ${stderr}` };
    }

    // Copy config files to the team repo
    const filesToSync = ["agents.json", "mcp.json", "lsp.json"];
    for (const file of filesToSync) {
      const srcPath = join(configDir, file);
      if (existsSync(srcPath)) {
        const content = await readFile(srcPath, "utf-8");
        await writeFile(join(tempDir, file), content, "utf-8");
      }
    }

    // Copy profiles
    const profilesDir = join(configDir, "profiles");
    const tempProfilesDir = join(tempDir, "profiles");
    if (existsSync(profilesDir)) {
      if (!existsSync(tempProfilesDir)) {
        await mkdir(tempProfilesDir, { recursive: true });
      }
      const { readdirSync } = await import("fs");
      const profiles = readdirSync(profilesDir).filter((f) => f.endsWith(".json"));
      for (const profile of profiles) {
        const content = await readFile(join(profilesDir, profile), "utf-8");
        await writeFile(join(tempProfilesDir, profile), content, "utf-8");
      }
    }

    // Git add, commit, push
    const addProc = Bun.spawn(["git", "add", "."], { cwd: tempDir, stdout: "pipe", stderr: "pipe" });
    await addProc.exited;

    const commitProc = Bun.spawn(["git", "commit", "-m", `sync: update config from ${new Date().toISOString()}`], {
      cwd: tempDir,
      stdout: "pipe",
      stderr: "pipe",
    });
    await commitProc.exited;

    if (commitProc.exitCode !== 0) {
      // No changes to commit
      await cleanup(tempDir);
      return { success: true };
    }

    const pushProc = Bun.spawn(["git", "push", "origin", teamConfig.branch], {
      cwd: tempDir,
      stdout: "pipe",
      stderr: "pipe",
    });
    await pushProc.exited;

    if (pushProc.exitCode !== 0) {
      const stderr = await new Response(pushProc.stderr).text();
      await cleanup(tempDir);
      return { success: false, error: `Failed to push: ${stderr}` };
    }

    // Update last sync time
    teamConfig.lastSync = new Date().toISOString();
    await saveTeamConfig(teamConfig);

    await cleanup(tempDir);
    return { success: true };
  } catch (err: any) {
    await cleanup(tempDir);
    return { success: false, error: err.message };
  }
}

/**
 * Pull latest config from the team repository.
 */
export async function pullTeamConfig(): Promise<{ success: boolean; error?: string }> {
  const teamConfig = await loadTeamConfig();

  if (!teamConfig) {
    return { success: false, error: "Team sync not initialized. Run: opencode-jce team init <git-url>" };
  }

  // Validate repo URL and branch
  try {
    const parsed = new URL(teamConfig.repoUrl);
    if (parsed.protocol !== "https:" && parsed.protocol !== "git:") {
      return { success: false, error: "Team repo URL must use https: or git: protocol" };
    }
  } catch {
    return { success: false, error: "Team repo URL is not a valid URL" };
  }
  if (!/^[a-zA-Z0-9._\/-]+$/.test(teamConfig.branch)) {
    return { success: false, error: "Team branch name contains invalid characters" };
  }
  if (teamConfig.branch.includes("..")) {
    return { success: false, error: "Branch name must not contain '..' sequences" };
  }

  const configDir = getConfigDir();
  const tempDir = join(configDir, ".team-sync");

  try {
    // Clone the team repo
    if (existsSync(tempDir)) {
      await cleanup(tempDir);
    }

    const proc = Bun.spawn(["git", "clone", "--depth", "1", "--branch", teamConfig.branch, teamConfig.repoUrl, tempDir], {
      stdout: "pipe",
      stderr: "pipe",
    });
    await proc.exited;

    if (proc.exitCode !== 0) {
      const stderr = await new Response(proc.stderr).text();
      return { success: false, error: `Failed to clone team repo: ${stderr}` };
    }

    // Copy config files from team repo to local config
    const filesToSync = ["agents.json", "mcp.json", "lsp.json"];
    for (const file of filesToSync) {
      const srcPath = join(tempDir, file);
      const dstPath = join(configDir, file);
      if (existsSync(srcPath)) {
        // Backup existing before overwrite
        if (existsSync(dstPath)) {
          const backupPath = dstPath + ".team-backup";
          const existing = await readFile(dstPath, "utf-8");
          await writeFile(backupPath, existing, "utf-8");
        }
        // Validate JSON before writing
        const content = await readFile(srcPath, "utf-8");
        try { JSON.parse(content); } catch { continue; } // skip invalid JSON
        // Basic structure validation for known config files
        if (file === "agents.json") {
          const parsed = JSON.parse(content);
          if (!parsed.agents || !Array.isArray(parsed.agents)) continue;
        }
        if (file === "mcp.json") {
          const parsed = JSON.parse(content);
          if (!parsed.mcpServers || typeof parsed.mcpServers !== "object") continue;
        }
        if (file === "lsp.json") {
          const parsed = JSON.parse(content);
          if (!parsed.lsp || typeof parsed.lsp !== "object") continue;
        }
        await writeFile(dstPath, content, "utf-8");
      }
    }

    // Copy profiles
    const tempProfilesDir = join(tempDir, "profiles");
    const profilesDir = join(configDir, "profiles");
    if (existsSync(tempProfilesDir)) {
      if (!existsSync(profilesDir)) {
        await mkdir(profilesDir, { recursive: true });
      }
      const { readdirSync } = await import("fs");
      const profiles = readdirSync(tempProfilesDir).filter((f) => f.endsWith(".json"));
      for (const profile of profiles) {
        const resolvedDst = resolve(join(profilesDir, profile));
        if (!resolvedDst.startsWith(resolve(profilesDir) + sep)) continue; // skip traversal
        const srcProfile = join(tempProfilesDir, profile);
        const dstProfile = join(profilesDir, profile);
        // Backup existing before overwrite
        if (existsSync(dstProfile)) {
          const backupPath = dstProfile + ".team-backup";
          const existing = await readFile(dstProfile, "utf-8");
          await writeFile(backupPath, existing, "utf-8");
        }
        // Validate JSON before writing
        const content = await readFile(srcProfile, "utf-8");
        try { JSON.parse(content); } catch { continue; } // skip invalid JSON
        await writeFile(dstProfile, content, "utf-8");
      }
    }

    // Update last sync time
    teamConfig.lastSync = new Date().toISOString();
    await saveTeamConfig(teamConfig);

    await cleanup(tempDir);
    return { success: true };
  } catch (err: any) {
    await cleanup(tempDir);
    return { success: false, error: err.message };
  }
}

/**
 * Get team sync status.
 */
export async function getTeamStatus(): Promise<{
  initialized: boolean;
  repoUrl?: string;
  branch?: string;
  lastSync?: string;
}> {
  const config = await loadTeamConfig();

  if (!config) {
    return { initialized: false };
  }

  return {
    initialized: true,
    repoUrl: config.repoUrl,
    branch: config.branch,
    lastSync: config.lastSync,
  };
}

/**
 * Clean up temporary directory.
 */
async function cleanup(dir: string): Promise<void> {
  try {
    const { rmSync } = await import("fs");
    rmSync(dir, { recursive: true, force: true });
  } catch {
    // Ignore cleanup errors
  }
}

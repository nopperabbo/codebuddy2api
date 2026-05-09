import { existsSync } from "fs";
import { readFile, writeFile, mkdir, copyFile } from "fs/promises";
import { join } from "path";
import { platform } from "os";
import { createInterface } from "readline";
import chalk from "chalk";
import { getConfigDir, loadConfigFile, getConfigPath } from "./config.js";
import type { CheckResult, LspConfig } from "../types.js";
import { success, warn, info, error } from "./ui.js";

// ─── Types ───────────────────────────────────────────────────

export interface FixResult {
  name: string;
  fixed: boolean;
  message: string;
}

// ─── Helpers ─────────────────────────────────────────────────

async function commandExists(command: string): Promise<boolean> {
  try {
    const isWindows = platform() === "win32";
    const checkCmd = isWindows ? "where" : "which";
    const proc = Bun.spawn([checkCmd, command], {
      stdout: "pipe",
      stderr: "pipe",
    });
    const exitCode = await proc.exited;
    return exitCode === 0;
  } catch {
    return false;
  }
}

async function runCommand(command: string, args: string[]): Promise<{ success: boolean; output: string }> {
  try {
    const proc = Bun.spawn([command, ...args], {
      stdout: "pipe",
      stderr: "pipe",
    });
    // Read stdout and stderr concurrently to avoid deadlock
    const [output, stderr] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
    ]);
    const exitCode = await proc.exited;
    return { success: exitCode === 0, output: output || stderr };
  } catch (err: any) {
    return { success: false, output: err.message };
  }
}

// ─── Fix: Missing Config Files ───────────────────────────────

export async function fixMissingConfigs(): Promise<FixResult[]> {
  const results: FixResult[] = [];
  const configDir = getConfigDir();

  // Ensure config directory exists
  if (!existsSync(configDir)) {
    await mkdir(configDir, { recursive: true });
    results.push({ name: "Config Directory", fixed: true, message: `Created: ${configDir}` });
  }

  // Ensure subdirectories exist
  const subdirs = ["profiles", "prompts", "skills"];
  for (const dir of subdirs) {
    const dirPath = join(configDir, dir);
    if (!existsSync(dirPath)) {
      await mkdir(dirPath, { recursive: true });
      results.push({ name: `${dir}/`, fixed: true, message: `Created directory` });
    }
  }

  // Check for missing main config files — try to restore from repo defaults
  const requiredFiles = ["agents.json", "mcp.json", "lsp.json"];
  for (const file of requiredFiles) {
    const filePath = join(configDir, file);
    if (!existsSync(filePath)) {
      // Try to download from GitHub
      try {
        const url = `https://raw.githubusercontent.com/JCETools-Petra/JCE-Opencode-Tools/main/config/${file}`;
        const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
        if (response.ok) {
          const content = await response.text();
          try { JSON.parse(content); } catch { continue; } // Skip non-JSON responses
          await writeFile(filePath, content, "utf-8");
          results.push({ name: file, fixed: true, message: "Downloaded from repository" });
        } else {
          results.push({ name: file, fixed: false, message: "Could not download — create manually" });
        }
      } catch {
        results.push({ name: file, fixed: false, message: "No internet — cannot restore" });
      }
    }
  }

  return results;
}

// ─── Fix: Missing LSP Servers ────────────────────────────────

interface MissingLsp {
  name: string;
  command: string;
  installCommand: string;
  isNpm: boolean;
}

async function promptUser(question: string): Promise<string> {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

export async function fixMissingLsp(): Promise<FixResult[]> {
  const results: FixResult[] = [];

  let lspConfig: LspConfig;
  try {
    lspConfig = await loadConfigFile<LspConfig>("lsp.json");
  } catch {
    results.push({ name: "LSP Config", fixed: false, message: "Cannot load lsp.json — run fix for configs first" });
    return results;
  }

  // Find all missing LSP servers
  const servers = Object.entries(lspConfig.lsp);
  const missingServers: MissingLsp[] = [];

  for (const [name, entry] of servers) {
    const exists = await commandExists(entry.command);
    if (!exists) {
      missingServers.push({
        name,
        command: entry.command,
        installCommand: entry.installCommand,
        isNpm: entry.installCommand.startsWith("npm install"),
      });
    }
  }

  if (missingServers.length === 0) {
    return results;
  }

  // Display missing LSP servers with numbers
  console.log();
  console.log(chalk.white("  Missing LSP servers:"));
  console.log();

  missingServers.forEach((server, index) => {
    const num = String(index + 1).padStart(2);
    const tag = server.isNpm ? chalk.green("[npm]") : chalk.yellow("[manual]");
    console.log(`  ${num}. ${server.name} ${tag} — ${chalk.dim(server.installCommand)}`);
  });

  console.log();
  console.log(chalk.yellow("  a = Install all fixable    s = Skip"));
  console.log(chalk.yellow("  Or enter numbers: 1,3,5"));
  console.log();

  const choice = await promptUser("  Your choice: ");

  // Parse selection
  let selected: MissingLsp[] = [];

  if (/^[aA]$/.test(choice)) {
    selected = missingServers.filter((s) => s.isNpm);
    // Report non-npm as not auto-fixable
    for (const server of missingServers.filter((s) => !s.isNpm)) {
      results.push({
        name: `LSP: ${server.name}`,
        fixed: false,
        message: `Not auto-fixable. Run manually: ${server.installCommand}`,
      });
    }
  } else if (/^[sS]?$/.test(choice)) {
    info("Skipping LSP fix.");
    return results;
  } else {
    const nums = choice.split(",").map((n) => parseInt(n.trim(), 10)).filter((n) => !isNaN(n));
    for (const num of nums) {
      const server = missingServers[num - 1];
      if (server) {
        if (server.isNpm) {
          selected.push(server);
        } else {
          results.push({
            name: `LSP: ${server.name}`,
            fixed: false,
            message: `Not auto-fixable. Run manually: ${server.installCommand}`,
          });
        }
      }
    }
  }

  if (selected.length === 0) {
    info("No npm-based LSP servers selected.");
    return results;
  }

  // Check if npm is available
  const hasNpm = await commandExists("npm");
  if (!hasNpm) {
    for (const server of selected) {
      results.push({
        name: `LSP: ${server.name}`,
        fixed: false,
        message: "npm not found — install Node.js first",
      });
    }
    return results;
  }

  // Install selected servers
  console.log();
  info(`Installing ${selected.length} LSP server(s)...`);
  console.log();

  for (const server of selected) {
    process.stdout.write(`  Installing ${server.name}... `);
    const isWindows = platform() === "win32";
    const proc = Bun.spawn(
      isWindows ? ["cmd", "/c", server.installCommand] : ["sh", "-c", server.installCommand],
      { stdout: "pipe", stderr: "pipe" }
    );
    const [output, stderr] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
    ]);
    const exitCode = await proc.exited;
    const result = { success: exitCode === 0, output: output || stderr };
    if (result.success) {
      console.log(chalk.green("[OK]"));
      results.push({ name: `LSP: ${server.name}`, fixed: true, message: "Installed via npm" });
    } else {
      console.log(chalk.red("[FAIL]"));
      results.push({ name: `LSP: ${server.name}`, fixed: false, message: `Install failed: ${result.output.slice(0, 100)}` });
    }
  }

  return results;
}

// ─── Fix: Missing Tools ──────────────────────────────────────

export async function fixMissingTools(): Promise<FixResult[]> {
  const results: FixResult[] = [];
  const isWindows = platform() === "win32";

  // Check OpenCode CLI
  const hasOpencode = await commandExists("opencode");
  if (!hasOpencode) {
    const hasBun = await commandExists("bun");
    if (hasBun) {
      const result = await runCommand("bun", ["install", "-g", "opencode"]);
      if (result.success) {
        results.push({ name: "OpenCode CLI", fixed: true, message: "Installed via bun" });
      } else {
        results.push({ name: "OpenCode CLI", fixed: false, message: "bun install -g opencode failed" });
      }
    } else {
      results.push({ name: "OpenCode CLI", fixed: false, message: "Bun not installed — install Bun first" });
    }
  }

  return results;
}

// ─── Fix: Merge LSP to opencode.json ─────────────────────────

export async function fixLspConfig(): Promise<FixResult[]> {
  const results: FixResult[] = [];

  try {
    // Try multiple ways to find the CLI
    const configDir = getConfigDir();
    const cliPath = join(configDir, "cli", "src", "index.ts");
    const hasGlobalCli = await commandExists("opencode-jce");

    if (hasGlobalCli) {
      // Prefer globally installed CLI
      const result = await runCommand("opencode-jce", ["setup", "--merge-lsp"]);
      if (result.success) {
        results.push({ name: "opencode.json LSP", fixed: true, message: "LSP servers merged into opencode.json" });
      } else {
        results.push({ name: "opencode.json LSP", fixed: false, message: "Merge failed — run 'opencode-jce setup --merge-lsp' manually" });
      }
    } else if (existsSync(cliPath)) {
      // Fallback to local CLI in config dir
      const result = await runCommand("bun", ["run", cliPath, "setup", "--merge-lsp"]);
      if (result.success) {
        results.push({ name: "opencode.json LSP", fixed: true, message: "LSP servers merged into opencode.json" });
      } else {
        results.push({ name: "opencode.json LSP", fixed: false, message: "Merge failed — run 'opencode-jce setup --merge-lsp' manually" });
      }
    } else {
      results.push({ name: "opencode.json LSP", fixed: false, message: "CLI not found — reinstall opencode-jce" });
    }
  } catch {
    results.push({ name: "opencode.json LSP", fixed: false, message: "Unexpected error during LSP merge" });
  }

  return results;
}

// ─── Fix: Missing context-keeper MCP ─────────────────────────

export async function fixContextKeeper(): Promise<FixResult[]> {
  const results: FixResult[] = [];
  const configDir = getConfigDir();
  const opencodeJsonPath = join(configDir, "opencode.json");
  const contextKeeperPath = join(configDir, "cli", "src", "mcp", "context-keeper.ts");

  // Check if context-keeper.ts exists
  if (!existsSync(contextKeeperPath)) {
    results.push({
      name: "context-keeper file",
      fixed: false,
      message: `File missing: ${contextKeeperPath}. Run 'opencode-jce update' or reinstall.`,
    });
    return results;
  }

  if (!existsSync(opencodeJsonPath)) {
    const { buildDefaultOpenCodeJson } = await import("./opencode-json-template.js");
    const template = buildDefaultOpenCodeJson(configDir);
    await writeFile(
      opencodeJsonPath,
      JSON.stringify(template, null, 2) + "\n",
      "utf-8"
    );
    results.push({
      name: "opencode.json",
      fixed: true,
      message: "Created OpenCode config with MCP servers pre-configured.",
    });
  }

  try {
    const content = await readFile(opencodeJsonPath, "utf-8");
    const config = JSON.parse(content);

    if (!config.mcp) config.mcp = {};

    if (config.mcp["context-keeper"]) {
      // Already registered — nothing to fix
      return results;
    }

    // Normalize path (forward slashes)
    const normalizedPath = contextKeeperPath.replace(/\\/g, "/");

    config.mcp["context-keeper"] = {
      type: "local",
      command: ["bun", "run", normalizedPath],
      enabled: true,
    };

    await writeFile(opencodeJsonPath, JSON.stringify(config, null, 2) + "\n");
    results.push({
      name: "context-keeper",
      fixed: true,
      message: "Registered in opencode.json. Restart OpenCode to activate.",
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    results.push({ name: "context-keeper", fixed: false, message: `Failed: ${msg}` });
  }

  return results;
}

// ─── Master Fix Function ─────────────────────────────────────

export async function runAllFixes(failedChecks: CheckResult[]): Promise<FixResult[]> {
  const allResults: FixResult[] = [];

  const hasConfigErrors = failedChecks.some(
    (r) => r.name.includes("Config") || r.name.includes(".json") || r.name.includes("profiles")
  );
  const hasLspErrors = failedChecks.some((r) => r.name.startsWith("LSP:"));
  const hasToolErrors = failedChecks.some(
    (r) => r.name === "OpenCode CLI" && r.status !== "pass"
  );
  const hasContextKeeperError = failedChecks.some(
    (r) => r.name.includes("context-keeper") && r.status !== "pass"
  );

  // Fix in order: configs → tools → context-keeper → LSP → merge
  if (hasConfigErrors) {
    info("Fixing missing configuration files...");
    const configResults = await fixMissingConfigs();
    allResults.push(...configResults);
  }

  if (hasToolErrors) {
    info("Fixing missing tools...");
    const toolResults = await fixMissingTools();
    allResults.push(...toolResults);
  }

  if (hasContextKeeperError) {
    info("Fixing context-keeper MCP registration...");
    const ckResults = await fixContextKeeper();
    allResults.push(...ckResults);
  }

  if (hasLspErrors) {
    info("Fixing missing LSP servers (npm-based only)...");
    const lspResults = await fixMissingLsp();
    allResults.push(...lspResults);

    // After installing LSP servers, merge into opencode.json
    const hasNewLsp = lspResults.some((r) => r.fixed);
    if (hasNewLsp) {
      info("Merging new LSP servers into opencode.json...");
      const mergeResults = await fixLspConfig();
      allResults.push(...mergeResults);
    }
  }

  return allResults;
}

import { Command } from "commander";
import { createInterface } from "readline";
import { existsSync } from "fs";
import { readFile, writeFile, mkdir, chmod } from "fs/promises";
import { join } from "path";
import chalk from "chalk";
import {
  getConfigDir,
  getOpenCodeConfigPath,
  loadOpenCodeConfig,
  buildOpenCodeLspConfig,
  mergeLspToOpenCodeConfig,
} from "../lib/config.js";
import { listProfiles, setActiveProfile } from "../lib/profiles.js";
import { initVersionFile } from "../lib/version.js";
import { banner, heading, info, success, warn, error } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";
import type { LspConfig } from "../types.js";

interface SetupPreferences {
  defaultProfile: string | null;
  apiKeys: {
    openai: string;
    anthropic: string;
  };
  enabledLsp: string[];
}

/**
 * Create a readline interface for interactive prompts.
 */
function createRl(): ReturnType<typeof createInterface> {
  return createInterface({
    input: process.stdin,
    output: process.stdout,
  });
}

/**
 * Ask a question and return the answer.
 */
function ask(rl: ReturnType<typeof createInterface>, question: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      resolve(answer.trim());
    });
  });
}

/**
 * Ask a yes/no question.
 */
async function askYesNo(rl: ReturnType<typeof createInterface>, question: string): Promise<boolean> {
  const answer = await ask(rl, question);
  return answer.toLowerCase() === "y" || answer.toLowerCase() === "yes";
}

/**
 * Step 1: Choose default profile.
 */
async function chooseProfile(rl: ReturnType<typeof createInterface>): Promise<string | null> {
  heading("Step 1: Default Profile");
  console.log();

  const profiles = await listProfiles();

  if (profiles.length === 0) {
    warn("No profiles found. Skipping profile selection.");
    return null;
  }

  info("Available profiles:");
  console.log();

  profiles.forEach((profile, index) => {
    const num = chalk.cyan(`  [${index + 1}]`);
    const name = chalk.bold(profile.id.padEnd(18));
    console.log(`${num} ${name}${profile.description}`);
    console.log(`       Provider: ${profile.provider} | Model: ${profile.model}`);
  });

  console.log();
  const answer = await ask(rl, `  Choose a profile (1-${profiles.length}, or press Enter to skip): `);

  if (!answer) {
    info("Skipped profile selection.");
    return null;
  }

  const index = parseInt(answer, 10) - 1;
  if (index >= 0 && index < profiles.length) {
    const selected = profiles[index];
    await setActiveProfile(selected.id);
    success(`Default profile set to: ${selected.name}`);
    return selected.id;
  }

  warn("Invalid selection. Skipping profile selection.");
  return null;
}

/**
 * Step 2: Configure API keys.
 */
async function configureApiKeys(rl: ReturnType<typeof createInterface>): Promise<{ openai: string; anthropic: string }> {
  heading("Step 2: API Keys");
  console.log();
  info("API keys are stored as environment variable names in your profile configs.");
  info("Enter your actual API keys below to save them to a local .env reference file.");
  info("(Press Enter to skip any key)");
  console.log();

  const openai = await ask(rl, "  OpenAI API Key (OPENAI_API_KEY): ");
  const anthropic = await ask(rl, "  Anthropic API Key (ANTHROPIC_API_KEY): ");

  if (openai || anthropic) {
    // Write a reference .env file in the config directory
    const configDir = getConfigDir();
    if (!existsSync(configDir)) {
      await mkdir(configDir, { recursive: true });
    }

    const shellEscape = (value: string): string => {
      return "'" + value.replace(/'/g, "'\\''") + "'";
    };
    const envLines: string[] = ["# OpenCode JCE API Keys", "# Source this file or add to your shell profile", ""];
    if (openai) envLines.push(`export OPENAI_API_KEY=${shellEscape(openai)}`);
    if (anthropic) envLines.push(`export ANTHROPIC_API_KEY=${shellEscape(anthropic)}`);
    envLines.push("");

    const envPath = join(configDir, "api-keys.env");
    await writeFile(envPath, envLines.join("\n"), "utf-8");
    // Restrict file permissions to owner-only (prevents other users from reading API keys)
    if (process.platform !== "win32") {
      await chmod(envPath, 0o600);
    }
    success(`API keys saved to: ${envPath}`);
    info(`Add \`source ${envPath}\` to your shell profile to load them automatically.`);
  } else {
    info("No API keys provided. Skipping.");
  }

  return { openai, anthropic };
}

/**
 * Step 3: Configure LSP servers.
 */
async function configureLsp(rl: ReturnType<typeof createInterface>): Promise<string[]> {
  heading("Step 3: LSP Servers");
  console.log();

  const configDir = getConfigDir();
  const lspPath = join(configDir, "lsp.json");

  if (!existsSync(lspPath)) {
    warn("lsp.json not found. Skipping LSP configuration.");
    return [];
  }

  let lspConfig: LspConfig;
  try {
    const content = await readFile(lspPath, "utf-8");
    lspConfig = JSON.parse(content) as LspConfig;
  } catch {
    warn("Could not parse lsp.json. Skipping LSP configuration.");
    return [];
  }

  const servers = Object.entries(lspConfig.lsp || {});
  if (servers.length === 0) {
    info("No LSP servers configured.");
    return [];
  }

  info("Available LSP servers:");
  console.log();

  const enabled: string[] = [];

  for (const [name, entry] of servers) {
    const answer = await askYesNo(rl, `  Enable ${chalk.bold(name)} (${entry.filetypes.join(", ")})? (y/N): `);
    if (answer) {
      enabled.push(name);
    }
  }

  if (enabled.length > 0) {
    // Detect which enabled servers are actually installed
    const { execFileSync } = await import("child_process");
    const installedCommands: string[] = [];

    for (const name of enabled) {
      const entry = lspConfig.lsp[name];
      if (!entry) continue;
      try {
        const whichCmd = process.platform === "win32" ? "where" : "which";
        execFileSync(whichCmd, [entry.command], { stdio: "ignore" });
        installedCommands.push(entry.command);
      } catch {
        warn(`${name}: ${entry.command} not found in PATH. Skipping merge.`);
      }
    }

    // Merge into opencode.json
    const lspServers = buildOpenCodeLspConfig(lspConfig, installedCommands);
    if (Object.keys(lspServers).length > 0) {
      const { added, skipped } = await mergeLspToOpenCodeConfig(lspServers);
      if (added.length > 0) {
        success(`Merged ${added.length} LSP server(s) into opencode.json: ${added.join(", ")}`);
      }
      if (skipped.length > 0) {
        info(`Skipped ${skipped.length} (already in opencode.json): ${skipped.join(", ")}`);
      }
    }

    success(`Enabled ${enabled.length} LSP server(s): ${enabled.join(", ")}`);
  } else {
    info("No LSP servers enabled.");
  }

  return enabled;
}

/**
 * Merge installed LSP servers into opencode.json (non-interactive).
 * Detects which LSP commands are in PATH and adds them to opencode.json.
 */
async function mergeLspNonInteractive(): Promise<void> {
  logCommandStart("setup --merge-lsp");

  const configDir = getConfigDir();
  const lspPath = join(configDir, "lsp.json");

  if (!existsSync(lspPath)) {
    warn("lsp.json not found. Cannot merge LSP config.");
    process.exit(EXIT_ERROR);
  }

  let lspConfig: LspConfig;
  try {
    const content = await readFile(lspPath, "utf-8");
    lspConfig = JSON.parse(content) as LspConfig;
  } catch {
    error("Could not parse lsp.json.");
    process.exit(EXIT_ERROR);
  }

  // Detect which LSP commands are installed
  const { execFileSync } = await import("child_process");
  const installedCommands: string[] = [];

  for (const [, entry] of Object.entries(lspConfig.lsp || {})) {
    try {
      const whichCmd = process.platform === "win32" ? "where" : "which";
      execFileSync(whichCmd, [entry.command], { stdio: "ignore" });
      installedCommands.push(entry.command);
    } catch {
      // Command not found — skip
    }
  }

  if (installedCommands.length === 0) {
    info("No LSP servers found in PATH. Nothing to merge.");
    process.exit(EXIT_SUCCESS);
  }

  // Build OpenCode LSP config from installed servers
  const lspServers = buildOpenCodeLspConfig(lspConfig, installedCommands);

  if (Object.keys(lspServers).length === 0) {
    info("No new LSP servers to add.");
    process.exit(EXIT_SUCCESS);
  }

  // Merge into opencode.json
  const { added, skipped } = await mergeLspToOpenCodeConfig(lspServers);

  if (added.length > 0) {
    success(`Added ${added.length} LSP server(s) to opencode.json: ${added.join(", ")}`);
  }
  if (skipped.length > 0) {
    info(`Skipped ${skipped.length} (already configured): ${skipped.join(", ")}`);
  }

  const configPath = getOpenCodeConfigPath();
  info(`Config: ${configPath}`);

  logCommandSuccess("setup --merge-lsp", `added=${added.length} skipped=${skipped.length}`);
  process.exit(EXIT_SUCCESS);
}

export const setupCommand = new Command("setup")
  .description("Interactive first-time setup wizard")
  .option("--merge-lsp", "Auto-detect installed LSP servers and merge into opencode.json")
  .action(async (options: { mergeLsp?: boolean }) => {
    // Non-interactive LSP merge mode
    if (options.mergeLsp) {
      await mergeLspNonInteractive();
      return;
    }

    logCommandStart("setup");
    banner();

    console.log(chalk.bold("  Welcome to the OpenCode JCE Setup Wizard!"));
    console.log("  This will guide you through configuring your environment.");
    console.log();

    const configDir = getConfigDir();
    if (!existsSync(configDir)) {
      error("Config directory not found. Please run the installer first.");
      info("  bash: curl -fsSL <install-url> | bash");
      info("  powershell: irm <install-url> | iex");
      logCommandError("setup", "Config directory not found");
      process.exit(EXIT_ERROR);
    }

    const rl = createRl();

    try {
      // Step 1: Profile
      const defaultProfile = await chooseProfile(rl);

      // Step 2: API Keys
      const apiKeys = await configureApiKeys(rl);

      // Step 3: LSP
      const enabledLsp = await configureLsp(rl);

      // Initialize version file
      await initVersionFile();

      // Summary
      console.log();
      heading("Setup Complete!");
      console.log();

      if (defaultProfile) {
        success(`Default profile: ${defaultProfile}`);
      }
      if (apiKeys.openai || apiKeys.anthropic) {
        success("API keys configured.");
      }
      if (enabledLsp.length > 0) {
        success(`LSP servers enabled: ${enabledLsp.join(", ")}`);
      }

      console.log();
      info("Next steps:");
      info("  • Run `opencode-jce doctor` to verify your setup");
      info("  • Run `opencode-jce use <profile>` to switch profiles");
      info("  • Run `opencode-jce validate` to check config files");
      console.log();

      logCommandSuccess("setup", `profile=${defaultProfile || "none"}, lsp=${enabledLsp.length}`);
    } finally {
      rl.close();
    }

    process.exit(EXIT_SUCCESS);
  });

import { Command } from "commander";
import { existsSync } from "fs";
import { rm, cp, mkdir } from "fs/promises";
import { join } from "path";
import { platform } from "os";
import { createInterface } from "readline";
import { getConfigDir } from "../lib/config.js";
import { banner, heading, info, success, warn, error } from "../lib/ui.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";

// ─── MCP Packages (from config/mcp.json) ────────────────────────────────────

const MCP_PACKAGES = [
  "@upstash/context7-mcp",
  "@modelcontextprotocol/server-github",
  "@modelcontextprotocol/server-filesystem",
  "@modelcontextprotocol/server-memory",
  "@playwright/mcp",
  "@modelcontextprotocol/server-sequential-thinking",
  "@modelcontextprotocol/server-postgres",
] as const;

// ─── LSP Servers (all that the installer can install) ────────────────────────

interface LspServerInfo {
  name: string;
  command: string; // Binary name to check if installed
  /** Uninstall strategies in order of preference. Tries each until one succeeds. */
  uninstallStrategies: string[][];
}

/**
 * Build the LSP server list with platform-appropriate uninstall commands.
 */
function buildLspServers(): LspServerInfo[] {
  const isWindows = platform() === "win32";
  const home = process.env.USERPROFILE || process.env.HOME || "";

  return [
    // npm-installed (cross-platform, always works)
    { name: "Python (pyright)", command: "pyright-langserver", uninstallStrategies: [["npm", "uninstall", "-g", "pyright"]] },
    { name: "TypeScript", command: "typescript-language-server", uninstallStrategies: [["npm", "uninstall", "-g", "typescript-language-server"]] },
    { name: "Bash", command: "bash-language-server", uninstallStrategies: [["npm", "uninstall", "-g", "bash-language-server"]] },
    { name: "YAML", command: "yaml-language-server", uninstallStrategies: [["npm", "uninstall", "-g", "yaml-language-server"]] },
    { name: "HTML/CSS/JSON", command: "vscode-json-language-server", uninstallStrategies: [["npm", "uninstall", "-g", "vscode-langservers-extracted"]] },
    { name: "Docker", command: "docker-langserver", uninstallStrategies: [["npm", "uninstall", "-g", "dockerfile-language-server-nodejs"]] },
    { name: "SQL", command: "sql-language-server", uninstallStrategies: [["npm", "uninstall", "-g", "sql-language-server"]] },
    { name: "PHP (intelephense)", command: "intelephense", uninstallStrategies: [["npm", "uninstall", "-g", "intelephense"]] },
    { name: "Svelte", command: "svelteserver", uninstallStrategies: [["npm", "uninstall", "-g", "svelte-language-server"]] },
    { name: "Vue", command: "vue-language-server", uninstallStrategies: [["npm", "uninstall", "-g", "@vue/language-server"]] },
    { name: "Tailwind CSS", command: "tailwindcss-language-server", uninstallStrategies: [["npm", "uninstall", "-g", "@tailwindcss/language-server"]] },
    { name: "GraphQL", command: "graphql-lsp", uninstallStrategies: [["npm", "uninstall", "-g", "graphql-language-service-cli"]] },

    // Rust-analyzer: bundled with rustup toolchain — remove component or delete binary
    { name: "Rust (rust-analyzer)", command: "rust-analyzer", uninstallStrategies: isWindows
      ? [
          ["rustup", "component", "remove", "rust-analyzer"],
          ["cmd", "/c", "del", join(home, ".cargo", "bin", "rust-analyzer.exe")],
        ]
      : [
          ["rustup", "component", "remove", "rust-analyzer"],
          ["rm", "-f", join(home, ".cargo", "bin", "rust-analyzer")],
        ]
    },

    // Go — delete the binary directly on Windows since go clean may not work
    { name: "Go (gopls)", command: "gopls", uninstallStrategies: isWindows
      ? [["cmd", "/c", "del", join(home, "go", "bin", "gopls.exe")], ["go", "clean", "-i", "golang.org/x/tools/gopls@latest"]]
      : [["go", "clean", "-i", "golang.org/x/tools/gopls@latest"]]
    },

    // Ruby
    { name: "Ruby (solargraph)", command: "solargraph", uninstallStrategies: [["gem", "uninstall", "solargraph", "-x"]] },

    // .NET (csharp-ls on Windows, omnisharp on macOS/Linux)
    { name: "C# (csharp-ls)", command: "csharp-ls", uninstallStrategies: isWindows
      ? [["dotnet", "tool", "uninstall", "-g", "csharp-ls"]]
      : [["dotnet", "tool", "uninstall", "-g", "csharp-ls"], ["dotnet", "tool", "uninstall", "-g", "omnisharp"]]
    },

    // C/C++ (clangd) — needs admin on Windows
    { name: "C/C++ (clangd)", command: "clangd", uninstallStrategies: isWindows
      ? [
          ["winget", "uninstall", "--id", "LLVM.LLVM", "--force", "--accept-source-agreements", "--silent"],
          ["scoop", "uninstall", "llvm"],
          ["choco", "uninstall", "llvm"],
        ]
      : [["brew", "uninstall", "llvm"], ["apt-get", "remove", "-y", "clangd"]]
    },

    // Java (jdtls) — on Windows installed as shim + downloaded LSP
    { name: "Java (jdtls)", command: "jdtls", uninstallStrategies: isWindows
      ? [["cmd", "/c", "del", join(home, ".opencode-jce", "bin", "jdtls.cmd")]]
      : [["brew", "uninstall", "jdtls"]]
    },

    // Cargo-installed tools
    { name: "TOML (taplo)", command: "taplo", uninstallStrategies: [["cargo", "uninstall", "taplo-cli"]] },

    // Marksman — needs admin on Windows
    { name: "Markdown (marksman)", command: "marksman", uninstallStrategies: isWindows
      ? [
          ["winget", "uninstall", "--id", "Artempyanykh.Marksman", "--force", "--accept-source-agreements", "--silent"],
          ["scoop", "uninstall", "marksman"],
          ["cargo", "uninstall", "marksman"],
        ]
      : [["brew", "uninstall", "marksman"], ["cargo", "uninstall", "marksman"]]
    },

    // Zig
    { name: "Zig (zls)", command: "zls", uninstallStrategies: isWindows
      ? [["scoop", "uninstall", "zls"], ["cargo", "uninstall", "zls"]]
      : [["brew", "uninstall", "zls"], ["cargo", "uninstall", "zls"]]
    },

    // Dart
    { name: "Dart", command: "dart", uninstallStrategies: isWindows
      ? [["choco", "uninstall", "dart-sdk"], ["scoop", "uninstall", "dart"]]
      : [["brew", "uninstall", "dart"]]
    },

    // Lua — installed via winget on Windows
    { name: "Lua", command: "lua-language-server", uninstallStrategies: isWindows
      ? [
          ["winget", "uninstall", "--id", "LuaLS.lua-language-server", "--force", "--accept-source-agreements", "--silent"],
          ["scoop", "uninstall", "lua-language-server"],
        ]
      : [["brew", "uninstall", "lua-language-server"]]
    },

    // Kotlin
    { name: "Kotlin", command: "kotlin-language-server", uninstallStrategies: isWindows
      ? [["scoop", "uninstall", "kotlin-language-server"]]
      : [["brew", "uninstall", "kotlin-language-server"]]
    },

    // Terraform
    { name: "Terraform", command: "terraform-ls", uninstallStrategies: isWindows
      ? [["winget", "uninstall", "--id", "HashiCorp.Terraform", "--force", "--accept-source-agreements", "--silent"]]
      : [["brew", "uninstall", "terraform-ls"]]
    },

    // Elixir
    { name: "Elixir", command: "elixir-ls", uninstallStrategies: isWindows
      ? [["scoop", "uninstall", "elixir-ls"]]
      : [["brew", "uninstall", "elixir-ls"]]
    },

    // Scala
    { name: "Scala (metals)", command: "metals", uninstallStrategies: isWindows
      ? [["cs", "uninstall", "metals"]]
      : [["brew", "uninstall", "metals"], ["cs", "uninstall", "metals"]]
    },
  ];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

interface CommandResult {
  ok: boolean;
  output: string;
}

async function runCommand(command: string, args: string[]): Promise<CommandResult> {
  try {
    const proc = Bun.spawn([command, ...args], { stdout: "pipe", stderr: "pipe" });
    // Timeout: 120s for winget (can be slow), 30s for others
    const timeoutMs = command === "winget" ? 120_000 : 30_000;
    const exitPromise = proc.exited;
    let timer: ReturnType<typeof setTimeout>;
    const timeoutPromise = new Promise<number>((_, reject) => {
      timer = setTimeout(() => { proc.kill(); reject(new Error("timeout")); }, timeoutMs);
    });
    const exitCode = await Promise.race([exitPromise, timeoutPromise]);
    clearTimeout(timer!);
    const output = await new Response(proc.stdout).text();
    return { ok: exitCode === 0, output };
  } catch {
    return { ok: false, output: "" };
  }
}

/**
 * Check if the current process is running with admin/elevated privileges.
 */
async function isRunningAsAdmin(): Promise<boolean> {
  if (platform() !== "win32") return process.getuid?.() === 0;
  try {
    const proc = Bun.spawn(["net", "session"], { stdout: "pipe", stderr: "pipe" });
    return (await proc.exited) === 0;
  } catch {
    return false;
  }
}

/**
 * Run a command elevated (as Administrator) on Windows via PowerShell.
 * Triggers UAC prompt automatically. Returns true if successful.
 */
async function runElevated(command: string, argsString: string): Promise<boolean> {
  try {
    // Escape single quotes in args to prevent PowerShell injection
    const safeCommand = command.replace(/'/g, "''");
    const safeArgs = argsString.replace(/'/g, "''");
    const proc = Bun.spawn([
      "powershell.exe", "-NoProfile", "-Command",
      `Start-Process '${safeCommand}' -ArgumentList '${safeArgs}' -Verb RunAs -Wait`
    ], { stdout: "pipe", stderr: "pipe" });

    const timeoutMs = 120_000;
    const exitPromise = proc.exited;
    const timeoutPromise = new Promise<number>((_, reject) =>
      setTimeout(() => { proc.kill(); reject(new Error("timeout")); }, timeoutMs)
    );
    const exitCode = await Promise.race([exitPromise, timeoutPromise]);
    return exitCode === 0;
  } catch {
    return false;
  }
}

async function commandExists(cmd: string): Promise<boolean> {
  const isWindows = platform() === "win32";

  if (isWindows) {
    // First try `where` (checks PATH)
    try {
      const proc = Bun.spawn(["where", cmd], { stdout: "pipe", stderr: "pipe" });
      if ((await proc.exited) === 0) return true;
    } catch {}

    // Also check common Windows installation paths (matching install.ps1 behavior)
    const home = process.env.USERPROFILE || "";
    const localAppData = process.env.LOCALAPPDATA || join(home, "AppData", "Local");

    // Check all possible extensions
    const extensions = [".exe", ".cmd", ".bat", ""];
    const basePaths = [
      join(home, "go", "bin"),
      join(home, ".dotnet", "tools"),
      join(home, ".cargo", "bin"),
      join(home, ".opencode-jce", "bin"),
      `C:\\Program Files\\LLVM\\bin`,
      `C:\\Program Files\\Go\\bin`,
      join(home, ".rustup", "toolchains", "stable-x86_64-pc-windows-msvc", "bin"),
      join(localAppData, "Programs", "lua-language-server", "bin"),
      join(localAppData, "Microsoft", "WinGet", "Links"),
    ];

    for (const base of basePaths) {
      for (const ext of extensions) {
        if (existsSync(join(base, `${cmd}${ext}`))) return true;
      }
    }

    return false;
  }

  try {
    const proc = Bun.spawn(["which", cmd], { stdout: "pipe", stderr: "pipe" });
    return (await proc.exited) === 0;
  } catch {
    return false;
  }
}

function askConfirmation(question: string): Promise<boolean> {
  const rl = createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      const normalized = answer.trim().toLowerCase();
      resolve(normalized === "y" || normalized === "yes");
    });
  });
}

// ─── Uninstall Steps ─────────────────────────────────────────────────────────

interface UninstallResult {
  configRemoved: boolean;
  configBackupPath: string | null;
  mcpCacheCleaned: boolean;
  lspRemoved: string[];
  lspSkipped: string[];
  opencodejceRemoved: boolean;
  opencodeRemoved: boolean;
}

async function removeConfigDirectory(force: boolean, keepCli: boolean): Promise<{ removed: boolean; backupPath: string | null }> {
  const configDir = getConfigDir();
  const cliDir = join(configDir, "cli");
  const hasCli = existsSync(cliDir);

  console.log();
  heading("1. Config Directory");
  info(`Path: ${configDir}`);

  if (!existsSync(configDir)) {
    warn("Config directory tidak ditemukan. Skip.");
    return { removed: false, backupPath: null };
  }

  if (!force) {
    const confirmed = await askConfirmation("  Hapus config directory? Backup akan dibuat terlebih dahulu. (y/N): ");
    if (!confirmed) {
      info("Config directory dipertahankan.");
      return { removed: false, backupPath: null };
    }
  }

  // Create backup
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const backupDir = `${configDir}.bak.${timestamp}`;

  info(`Membuat backup: ${backupDir}`);
  try {
    await mkdir(backupDir, { recursive: true });
    await cp(configDir, backupDir, { recursive: true });
    success(`Backup berhasil: ${backupDir}`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    error(`Gagal membuat backup: ${msg}`);
    return { removed: false, backupPath: null };
  }

  // If CLI lives inside config dir and user wants to keep it, preserve it
  let cliTempDir: string | null = null;
  if (hasCli && keepCli) {
    cliTempDir = join(configDir, "..", "opencode-cli-temp");
    try {
      await cp(cliDir, cliTempDir, { recursive: true });
    } catch {
      cliTempDir = null;
    }
  }

  // Remove config
  info("Menghapus config directory...");
  try {
    await rm(configDir, { recursive: true, force: true });
    success("Config directory dihapus.");
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    error(`Gagal menghapus config: ${msg}`);
    return { removed: false, backupPath: backupDir };
  }

  // Restore CLI if it was preserved
  if (cliTempDir && existsSync(cliTempDir)) {
    try {
      await mkdir(configDir, { recursive: true });
      await cp(cliTempDir, cliDir, { recursive: true });
      await rm(cliTempDir, { recursive: true, force: true });
      info("CLI source preserved di config directory.");
    } catch {
      warn("Gagal restore CLI. Jalankan: bun install -g opencode-jce");
    }
  }

  return { removed: true, backupPath: backupDir };
}

async function cleanMcpCache(force: boolean, keep: boolean): Promise<boolean> {
  console.log();
  heading("2. MCP Packages (npm/npx cache)");

  if (keep) {
    info("--keep-mcp flag aktif. MCP cache dipertahankan.");
    return false;
  }

  info("MCP servers dijalankan via npx dan tersimpan di npm cache:");
  for (const pkg of MCP_PACKAGES) {
    console.log(`    • ${pkg}`);
  }
  console.log();

  if (!force) {
    const confirmed = await askConfirmation("  Hapus MCP packages dari npm cache? (npm cache clean --force) (y/N): ");
    if (!confirmed) {
      info("npm cache dipertahankan.");
      return false;
    }
  }

  info("Membersihkan npm cache...");
  const result = await runCommand("npm", ["cache", "clean", "--force"]);

  if (result.ok) {
    success("npm cache berhasil dibersihkan (semua MCP packages dihapus).");
    return true;
  } else {
    warn("Gagal membersihkan npm cache. Coba jalankan manual: npm cache clean --force");
    return false;
  }
}

async function removeLspServers(force: boolean, keep: boolean): Promise<{ removed: string[]; skipped: string[] }> {
  console.log();
  heading("3. LSP Servers");

  const lspServers = buildLspServers();

  if (keep) {
    info("--keep-lsp flag aktif. LSP servers dipertahankan.");
    return { removed: [], skipped: lspServers.map((s) => s.name) };
  }

  // Check which LSP servers are actually installed
  info("Memeriksa LSP servers yang terinstall...");
  const installed: LspServerInfo[] = [];

  for (const server of lspServers) {
    const exists = await commandExists(server.command);
    if (exists) {
      installed.push(server);
    }
  }

  if (installed.length === 0) {
    info("Tidak ada LSP server yang terdeteksi terinstall.");
    return { removed: [], skipped: [] };
  }

  console.log();
  info(`LSP servers yang terinstall (${installed.length}):`);
  for (const server of installed) {
    console.log(`    ✓ ${server.name}`);
  }
  console.log();

  if (!force) {
    const confirmed = await askConfirmation("  Hapus LSP servers yang di-install oleh opencode-jce? (y/N): ");
    if (!confirmed) {
      info("LSP servers dipertahankan.");
      return { removed: [], skipped: installed.map((s) => s.name) };
    }
  }

  const isAdmin = await isRunningAsAdmin();
  const isWindows = platform() === "win32";

  const removed: string[] = [];
  const skipped: string[] = [];

  // Kill running LSP processes first (they lock the exe files)
  if (isWindows) {
    for (const server of installed) {
      const procName = server.command.replace(/\.exe$/, "");
      try {
        await runCommand("powershell.exe", ["-NoProfile", "-Command", `Stop-Process -Name '${procName}' -Force -ErrorAction SilentlyContinue`]);
      } catch {}
    }
    // Give OS time to release file locks
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  for (const server of installed) {
    info(`Menghapus ${server.name}...`);

    // Try each uninstall strategy in order until one succeeds
    let uninstalled = false;
    for (const strategy of server.uninstallStrategies) {
      const [cmd, ...args] = strategy;
      // Check if the uninstall tool exists first
      const toolExists = await commandExists(cmd);
      if (!toolExists) continue;

      const result = await runCommand(cmd, args);
      if (result.ok) {
        success(`${server.name} dihapus.`);
        removed.push(server.name);
        uninstalled = true;
        break;
      }

      // If winget failed, try elevated via PowerShell (triggers UAC)
      if (cmd === "winget" && isWindows) {
        info(`  Mencoba dengan elevated privileges...`);
        const argsStr = args.join(" ");
        const elevated = await runElevated("winget", argsStr);
        if (elevated) {
          success(`${server.name} dihapus (elevated).`);
          removed.push(server.name);
          uninstalled = true;
          break;
        }
      }
    }

    if (!uninstalled) {
      const fallbackCmd = server.uninstallStrategies[0].join(" ");
      warn(`Gagal menghapus ${server.name}. Coba manual: ${fallbackCmd}`);
      skipped.push(server.name);
    }
  }

  return { removed, skipped };
}

async function removeOpenCodeJceCli(force: boolean): Promise<boolean> {
  console.log();
  heading("4. opencode-jce CLI");

  if (!force) {
    const confirmed = await askConfirmation("  Hapus opencode-jce CLI? (y/N): ");
    if (!confirmed) {
      info("opencode-jce CLI dipertahankan.");
      return false;
    }
  }

  info("Menghapus opencode-jce (semua metode)...");

  let removed = false;

  // Try all possible ways opencode-jce could be installed
  const strategies = [
    { cmd: "bun", args: ["remove", "-g", "opencode-jce"], label: "bun global" },
    { cmd: "npm", args: ["uninstall", "-g", "opencode-jce"], label: "npm global" },
    { cmd: "bun", args: ["remove", "-g", "opencode-jce-tools"], label: "bun (alt name)" },
    { cmd: "npm", args: ["uninstall", "-g", "opencode-jce-tools"], label: "npm (alt name)" },
  ];

  for (const s of strategies) {
    const result = await runCommand(s.cmd, s.args);
    if (result.ok) {
      success(`  opencode-jce dihapus via ${s.label}.`);
      removed = true;
    }
  }

  // Also remove CLI source from config dir if it exists
  const cliDir = join(getConfigDir(), "cli");
  if (existsSync(cliDir)) {
    try {
      await rm(cliDir, { recursive: true, force: true });
      success("  CLI source directory dihapus.");
      removed = true;
    } catch {}
  }

  if (!removed) {
    warn("opencode-jce tidak ditemukan di package manager manapun.");
  }

  return removed;
}

async function removeOpenCodeCli(force: boolean): Promise<boolean> {
  console.log();
  heading("5. OpenCode CLI");

  if (!force) {
    const confirmed = await askConfirmation("  Hapus OpenCode CLI? (y/N): ");
    if (!confirmed) {
      info("OpenCode CLI dipertahankan.");
      return false;
    }
  }

  info("Menghapus opencode (semua metode)...");

  let removed = false;

  // Try ALL possible package names and managers
  const strategies = [
    { cmd: "npm", args: ["uninstall", "-g", "opencode-ai"], label: "npm opencode-ai" },
    { cmd: "npm", args: ["uninstall", "-g", "opencode"], label: "npm opencode" },
    { cmd: "npm", args: ["uninstall", "-g", "@anthropic/opencode"], label: "npm @anthropic/opencode" },
    { cmd: "bun", args: ["remove", "-g", "opencode"], label: "bun opencode" },
    { cmd: "bun", args: ["remove", "-g", "opencode-ai"], label: "bun opencode-ai" },
  ];

  for (const s of strategies) {
    const result = await runCommand(s.cmd, s.args);
    if (result.ok) {
      success(`  OpenCode dihapus via ${s.label}.`);
      removed = true;
    }
  }

  // Also try to remove the binary/shim directly if still exists
  if (platform() === "win32") {
    const npmDir = process.env.APPDATA ? join(process.env.APPDATA, "npm") : "";
    const filesToRemove = [
      join(npmDir, "opencode"),
      join(npmDir, "opencode.cmd"),
      join(npmDir, "opencode.ps1"),
    ];
    for (const f of filesToRemove) {
      if (existsSync(f)) {
        try {
          await rm(f, { force: true });
          removed = true;
        } catch {}
      }
    }
    // Remove node_modules package
    const nodeModulesDir = join(npmDir, "node_modules", "opencode-ai");
    if (existsSync(nodeModulesDir)) {
      try {
        await rm(nodeModulesDir, { recursive: true, force: true });
        success("  OpenCode node_modules dihapus.");
        removed = true;
      } catch {}
    }
  }

  if (!removed) {
    warn("OpenCode CLI tidak ditemukan di package manager manapun.");
  }

  return removed;
}

// ─── Summary ─────────────────────────────────────────────────────────────────

function printSummary(result: UninstallResult): void {
  console.log();
  heading("📋 Uninstall Summary");
  console.log();

  const removed: string[] = [];
  const kept: string[] = [];

  // Config
  if (result.configRemoved) {
    removed.push("Config directory");
    if (result.configBackupPath) {
      info(`Backup tersimpan di: ${result.configBackupPath}`);
    }
  } else {
    kept.push("Config directory");
  }

  // MCP cache
  if (result.mcpCacheCleaned) {
    removed.push("npm/npx cache (MCP packages)");
  } else {
    kept.push("npm/npx cache (MCP packages)");
  }

  // LSP
  if (result.lspRemoved.length > 0) {
    removed.push(`LSP servers: ${result.lspRemoved.join(", ")}`);
  }
  if (result.lspSkipped.length > 0) {
    kept.push(`LSP servers: ${result.lspSkipped.join(", ")}`);
  }

  // CLIs
  if (result.opencodejceRemoved) {
    removed.push("opencode-jce CLI");
  } else {
    kept.push("opencode-jce CLI");
  }

  if (result.opencodeRemoved) {
    removed.push("OpenCode CLI");
  } else {
    kept.push("OpenCode CLI");
  }

  // Print
  if (removed.length > 0) {
    console.log();
    success("Dihapus:");
    for (const item of removed) {
      console.log(`    • ${item}`);
    }
  }

  if (kept.length > 0) {
    console.log();
    info("Dipertahankan:");
    for (const item of kept) {
      console.log(`    • ${item}`);
    }
  }

  console.log();
  info("Git dan Bun TIDAK dihapus (digunakan oleh tools lain).");
  console.log();
}

// ─── Command ─────────────────────────────────────────────────────────────────

interface UninstallOptions {
  force?: boolean;
  keepLsp?: boolean;
  keepMcp?: boolean;
}

export const uninstallCommand = new Command("uninstall")
  .description("Remove OpenCode JCE configuration, MCP cache, LSP servers, and CLI tools")
  .option("--force", "Remove everything without asking (respects --keep-* flags)")
  .option("--keep-lsp", "Don't remove LSP servers (even with --force)")
  .option("--keep-mcp", "Don't remove MCP cache (even with --force)")
  .action(async (options: UninstallOptions) => {
    banner();
    heading("OpenCode JCE — Uninstaller");

    const force = options.force ?? false;
    const keepLsp = options.keepLsp ?? false;
    const keepMcp = options.keepMcp ?? false;

    if (force) {
      warn("Mode --force aktif: semua komponen akan dihapus tanpa konfirmasi.");
      if (keepLsp) info("--keep-lsp: LSP servers akan dipertahankan.");
      if (keepMcp) info("--keep-mcp: MCP cache akan dipertahankan.");
    }

    const result: UninstallResult = {
      configRemoved: false,
      configBackupPath: null,
      mcpCacheCleaned: false,
      lspRemoved: [],
      lspSkipped: [],
      opencodejceRemoved: false,
      opencodeRemoved: false,
    };

    // Determine if user wants to keep CLI (ask early so we know before deleting config)
    // In force mode, CLI will be removed. Otherwise ask later but we need to know now
    // to preserve cli/ dir inside config.
    let willRemoveCli = force;
    if (!force) {
      // Peek: does CLI live inside config dir?
      const cliInConfig = existsSync(join(getConfigDir(), "cli"));
      if (cliInConfig) {
        info("CLI source terdeteksi di dalam config directory.");
      }
    }

    // Step 1: Config directory (preserve cli/ if user won't remove CLI)
    const configResult = await removeConfigDirectory(force, !willRemoveCli);
    result.configRemoved = configResult.removed;
    result.configBackupPath = configResult.backupPath;

    // Step 2: MCP cache
    result.mcpCacheCleaned = await cleanMcpCache(force, keepMcp);

    // Step 3: LSP servers
    const lspResult = await removeLspServers(force, keepLsp);
    result.lspRemoved = lspResult.removed;
    result.lspSkipped = lspResult.skipped;

    // Step 4: opencode-jce CLI
    result.opencodejceRemoved = await removeOpenCodeJceCli(force);

    // Step 5: OpenCode CLI
    result.opencodeRemoved = await removeOpenCodeCli(force);

    // Summary
    printSummary(result);

    process.exit(EXIT_SUCCESS);
  });

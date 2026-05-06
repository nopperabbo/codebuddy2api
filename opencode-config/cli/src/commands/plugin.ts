import { Command } from "commander";
import chalk from "chalk";
import { loadPluginsRegistry, installPlugin, removePlugin, sanitizeGitUrl } from "../lib/plugins.js";
import { heading, info, success, error } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";

// ─── Subcommands ─────────────────────────────────────────────

const installCommand = new Command("install")
  .description("Install a plugin from a GitHub repository")
  .argument("<github-url>", "GitHub repository URL (e.g. https://github.com/user/repo)")
  .action(async (githubUrl: string) => {
    logCommandStart("plugin install", { url: sanitizeGitUrl(githubUrl) });

    info(`Installing plugin from: ${sanitizeGitUrl(githubUrl)}`);
    console.log();

    const result = await installPlugin(githubUrl);

    if (!result.success) {
      error(result.error!);
      logCommandError("plugin install", result.error!);
      process.exit(EXIT_ERROR);
    }

    const plugin = result.plugin!;
    success(`Plugin "${plugin.name}" v${plugin.version} installed successfully.`);
    info(`  Type: ${plugin.type}`);
    info(`  Description: ${plugin.description}`);
    logCommandSuccess("plugin install", `name=${plugin.name} version=${plugin.version}`);
    process.exit(EXIT_SUCCESS);
  });

const listCommand = new Command("list")
  .description("Show installed plugins")
  .action(async () => {
    logCommandStart("plugin list");

    const plugins = await loadPluginsRegistry();

    heading("Installed Plugins");
    console.log();

    if (plugins.length === 0) {
      info("No plugins installed.");
      info("Usage: opencode-jce plugin install <github-url>");
      process.exit(EXIT_SUCCESS);
    }

    for (const plugin of plugins) {
      const name = chalk.bold(plugin.name.padEnd(20));
      const version = chalk.dim(`v${plugin.version}`);
      const type = chalk.cyan(`[${plugin.type}]`);
      console.log(`  ${name} ${version.padEnd(12)} ${type}`);
      if (plugin.description) {
        console.log(`  ${"".padEnd(20)} ${chalk.dim(plugin.description)}`);
      }
    }

    console.log();
    info(`Total: ${plugins.length} plugin(s)`);
    logCommandSuccess("plugin list", `count=${plugins.length}`);
    process.exit(EXIT_SUCCESS);
  });

const removeCommand = new Command("remove")
  .description("Remove an installed plugin")
  .argument("<name>", "Plugin name to remove")
  .action(async (name: string) => {
    logCommandStart("plugin remove", { name });

    const result = await removePlugin(name);

    if (!result.success) {
      error(result.error!);
      logCommandError("plugin remove", result.error!);
      process.exit(EXIT_ERROR);
    }

    success(`Plugin "${name}" removed.`);
    logCommandSuccess("plugin remove", `name=${name}`);
    process.exit(EXIT_SUCCESS);
  });

// ─── Main Command ────────────────────────────────────────────

export const pluginCommand = new Command("plugin")
  .description("Manage community plugins (install, list, remove)")
  .addCommand(installCommand)
  .addCommand(listCommand)
  .addCommand(removeCommand);

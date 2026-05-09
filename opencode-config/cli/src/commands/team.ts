import { Command } from "commander";
import chalk from "chalk";
import { initTeamSync, pushTeamConfig, pullTeamConfig, getTeamStatus } from "../lib/team.js";
import { sanitizeGitUrl } from "../lib/plugins.js";
import { heading, info, success, error } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";

// ─── Subcommands ─────────────────────────────────────────────

const initCommand = new Command("init")
  .description("Initialize team config sync with a shared Git repository")
  .argument("<git-url>", "Git repository URL for team config sharing")
  .option("-b, --branch <branch>", "Branch to use", "main")
  .action(async (gitUrl: string, opts: { branch: string }) => {
    logCommandStart("team init", { url: sanitizeGitUrl(gitUrl), branch: opts.branch });

    info(`Initializing team sync with: ${sanitizeGitUrl(gitUrl)}`);
    console.log();

    const result = await initTeamSync(gitUrl, opts.branch);

    if (!result.success) {
      error(result.error!);
      logCommandError("team init", result.error!);
      process.exit(EXIT_ERROR);
    }

    success("Team sync initialized!");
    info(`  Repository: ${gitUrl}`);
    info(`  Branch: ${opts.branch}`);
    console.log();
    info("Next steps:");
    info("  Push your config:  opencode-jce team push");
    info("  Pull team config:  opencode-jce team pull");
    logCommandSuccess("team init", `url=${gitUrl} branch=${opts.branch}`);
    process.exit(EXIT_SUCCESS);
  });

const pushCommand = new Command("push")
  .description("Push current config to the team repository")
  .action(async () => {
    logCommandStart("team push");

    info("Pushing config to team repository...");
    console.log();

    const result = await pushTeamConfig();

    if (!result.success) {
      error(result.error!);
      logCommandError("team push", result.error!);
      process.exit(EXIT_ERROR);
    }

    success("Config pushed to team repository.");
    logCommandSuccess("team push");
    process.exit(EXIT_SUCCESS);
  });

const pullCommand = new Command("pull")
  .description("Pull latest config from the team repository")
  .action(async () => {
    logCommandStart("team pull");

    info("Pulling config from team repository...");
    console.log();

    const result = await pullTeamConfig();

    if (!result.success) {
      error(result.error!);
      logCommandError("team pull", result.error!);
      process.exit(EXIT_ERROR);
    }

    success("Config pulled from team repository.");
    info("Your local config has been updated with the team's latest settings.");
    logCommandSuccess("team pull");
    process.exit(EXIT_SUCCESS);
  });

const statusCommand = new Command("status")
  .description("Show team sync status")
  .action(async () => {
    logCommandStart("team status");

    const status = await getTeamStatus();

    heading("Team Sync Status");
    console.log();

    if (!status.initialized) {
      info("Team sync is not initialized.");
      info("Run: opencode-jce team init <git-url>");
      process.exit(EXIT_SUCCESS);
    }

    console.log(`  ${chalk.bold("Repository:")}  ${status.repoUrl}`);
    console.log(`  ${chalk.bold("Branch:")}      ${status.branch}`);
    console.log(`  ${chalk.bold("Last Sync:")}   ${status.lastSync}`);
    console.log();

    logCommandSuccess("team status");
    process.exit(EXIT_SUCCESS);
  });

// ─── Main Command ────────────────────────────────────────────

export const teamCommand = new Command("team")
  .description("Sync configs across a team via a shared Git repository")
  .addCommand(initCommand)
  .addCommand(pushCommand)
  .addCommand(pullCommand)
  .addCommand(statusCommand);

import { Command } from "commander";
import chalk from "chalk";
import { TokenTracker, detectOpenCodeDB } from "../lib/tokens.js";
import { heading, info, error, formatCost } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";

// ─── Formatting Helpers ──────────────────────────────────────

function formatNumber(n: number): string {
  return n.toLocaleString();
}

function makeBar(value: number, max: number, width: number = 20): string {
  if (max === 0) return "";
  const filled = Math.max(1, Math.round((value / max) * width));
  return "\u2588".repeat(filled);
}

// ─── Main Command ────────────────────────────────────────────

export const tokensCommand = new Command("tokens")
  .description("Show all token usage history from OpenCode")
  .action(async () => {
    logCommandStart("tokens");

    // 1. Detect database
    const dbPath = detectOpenCodeDB();

    if (!dbPath) {
      console.log();
      error("OpenCode database not found.");
      console.log();
      info("Make sure OpenCode has been run at least once.");
      info("Expected locations:");
      info("  Windows: ~/.local/share/opencode/opencode.db");
      info("  macOS:   ~/Library/Application Support/opencode/opencode.db");
      info("  Linux:   ~/.local/share/opencode/opencode.db");
      logCommandError("tokens", "Database not found");
      process.exit(EXIT_ERROR);
    }

    // 2. Validate schema
    const tracker = new TokenTracker(dbPath);

    if (!tracker.validateSchema()) {
      console.log();
      error("Database schema not recognized.");
      info("You may need to update opencode-jce to a newer version.");
      logCommandError("tokens", "Schema validation failed");
      process.exit(EXIT_ERROR);
    }

    // 3. Query and display
    let summary;
    try {
      summary = tracker.getSummary();
    } catch (err: any) {
      console.log();
      error(`Failed to read database: ${err.message}`);
      info("If OpenCode is running, try again in a moment.");
      logCommandError("tokens", err.message);
      process.exit(EXIT_ERROR);
    }

    // ─── Display ───────────────────────────────────────────

    console.log();
    console.log(chalk.cyan("══════════════════════════════════════════════"));
    console.log(chalk.cyan.bold("       Token Usage — All History"));
    console.log(chalk.cyan("══════════════════════════════════════════════"));
    console.log();

    if (summary.totalMessages === 0) {
      info("No token usage data found. Start using OpenCode to generate data.");
      process.exit(EXIT_SUCCESS);
    }

    // Summary stats
    console.log(`  ${chalk.bold("Sessions:")}        ${formatNumber(summary.totalSessions)}`);
    console.log(`  ${chalk.bold("Messages:")}        ${formatNumber(summary.totalMessages)}`);
    console.log();
    console.log(`  ${chalk.bold("Input Tokens:")}    ${chalk.white(formatNumber(summary.tokens.input))}`);
    console.log(`  ${chalk.bold("Output Tokens:")}   ${chalk.white(formatNumber(summary.tokens.output))}`);
    console.log(`  ${chalk.bold("Reasoning:")}       ${chalk.white(formatNumber(summary.tokens.reasoning))}`);
    console.log(`  ${chalk.bold("Cache Read:")}      ${chalk.dim(formatNumber(summary.tokens.cacheRead))}`);
    console.log(`  ${chalk.bold("Cache Write:")}     ${chalk.dim(formatNumber(summary.tokens.cacheWrite))}`);
    console.log(`  ${chalk.bold("Total Tokens:")}    ${chalk.green.bold(formatNumber(summary.tokens.total))}`);
    console.log();
    console.log(`  ${chalk.bold("Est. Cost:")}       ${chalk.yellow(formatCost(summary.totalCost))}`);

    // By Provider
    const providers = Object.entries(summary.byProvider).sort(
      (a, b) => b[1].tokens - a[1].tokens
    );

    if (providers.length > 0) {
      console.log();
      console.log(chalk.cyan("═══ By Provider ═══════════════════════════════"));
      console.log();

      const maxProviderTokens = providers[0][1].tokens;

      for (const [name, data] of providers) {
        const bar = makeBar(data.tokens, maxProviderTokens);
        const label = name.padEnd(16);
        const tokenStr = formatNumber(data.tokens).padStart(15);
        const msgStr = chalk.dim(`(${data.messages} msgs)`);
        console.log(`  ${chalk.bold(label)} ${tokenStr}  ${chalk.cyan(bar)}  ${msgStr}`);
      }
    }

    // By Model
    const models = Object.entries(summary.byModel).sort(
      (a, b) => b[1].tokens - a[1].tokens
    );

    if (models.length > 0) {
      console.log();
      console.log(chalk.cyan("═══ By Model ══════════════════════════════════"));
      console.log();

      const maxModelTokens = models[0][1].tokens;

      for (const [name, data] of models) {
        const bar = makeBar(data.tokens, maxModelTokens);
        const label = name.padEnd(28);
        const tokenStr = formatNumber(data.tokens).padStart(15);
        const msgStr = chalk.dim(`(${data.messages} msgs)`);
        console.log(`  ${chalk.bold(label)} ${tokenStr}  ${chalk.magenta(bar)}  ${msgStr}`);
      }
    }

    // Footer
    console.log();
    console.log(chalk.dim(`  Database: ${dbPath}`));
    console.log();

    logCommandSuccess("tokens", `messages=${summary.totalMessages} sessions=${summary.totalSessions}`);
    process.exit(EXIT_SUCCESS);
  });

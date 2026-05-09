import { Command } from "commander";
import chalk from "chalk";
import {
  loadFallbackConfig,
  checkProviderHealth,
  getAvailableProviders,
  getBestProvider,
  hasApiKey,
} from "../lib/fallback.js";
import { RateLimiter } from "../lib/ratelimit.js";
import { getConfigDir } from "../lib/config.js";
import { heading, info, success, warn, error } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess } from "../lib/logger.js";
import { EXIT_SUCCESS } from "../types.js";

// ─── Subcommands ─────────────────────────────────────────────

const statusCommand = new Command("status")
  .description("Show provider health and fallback order")
  .action(async () => {
    logCommandStart("fallback status");

    const configDir = getConfigDir();
    const config = await loadFallbackConfig(configDir);

    heading("Provider Fallback Status");
    console.log();

    const sorted = [...config.providers].sort((a, b) => a.priority - b.priority);

    for (const provider of sorted) {
      const keySet = hasApiKey(provider);
      const health = await checkProviderHealth(provider, config.timeoutMs);

      const priorityBadge = chalk.dim(`[priority: ${provider.priority}]`);
      const name = chalk.bold(provider.name.padEnd(12));

      if (health.healthy) {
        console.log(`  ${chalk.green("●")} ${name} ${chalk.green("healthy")}  ${priorityBadge}`);
      } else if (keySet) {
        console.log(`  ${chalk.yellow("●")} ${name} ${chalk.yellow("degraded")} ${priorityBadge}`);
        console.log(`    ${chalk.dim(health.reason || "Unknown issue")}`);
      } else {
        console.log(`  ${chalk.red("●")} ${name} ${chalk.red("no API key")} ${priorityBadge}`);
        console.log(`    ${chalk.dim(`Set ${provider.apiKeyEnv} environment variable`)}`);
      }
    }

    console.log();

    // Show best provider
    const best = await getBestProvider(config);
    if (best) {
      success(`Best available provider: ${chalk.bold(best.name)}`);
    } else {
      warn("No healthy providers available. Check your API keys and network.");
    }

    // Show rate limit state
    const limiter = new RateLimiter(configDir);
    const trackedProviders = limiter.getAllProviders();

    if (trackedProviders.length > 0) {
      heading("Rate Limit State");
      console.log();

      for (const providerName of trackedProviders) {
        const state = limiter.getState(providerName);
        const backoff = limiter.getBackoffTime(providerName);

        const name = chalk.bold(providerName.padEnd(12));
        if (backoff > 0) {
          const secs = Math.ceil(backoff / 1000);
          console.log(`  ${chalk.yellow("⏳")} ${name} backoff: ${secs}s remaining (${state.consecutiveErrors} errors)`);
        } else {
          console.log(`  ${chalk.green("✓")} ${name} no backoff (${state.requestsThisMinute} req/min)`);
        }
      }
      console.log();
    }

    logCommandSuccess("fallback status");
    process.exit(EXIT_SUCCESS);
  });

const testCommand = new Command("test")
  .description("Test all provider endpoints and show results")
  .action(async () => {
    logCommandStart("fallback test");

    const configDir = getConfigDir();
    const config = await loadFallbackConfig(configDir);

    heading("Testing Provider Endpoints");
    console.log();
    info(`Timeout: ${config.timeoutMs}ms`);
    console.log();

    const sorted = [...config.providers].sort((a, b) => a.priority - b.priority);

    for (const provider of sorted) {
      const name = chalk.bold(provider.name.padEnd(12));
      process.stdout.write(`  Testing ${name}... `);

      const start = Date.now();
      const result = await checkProviderHealth(provider, config.timeoutMs);
      const elapsed = Date.now() - start;

      if (result.healthy) {
        console.log(chalk.green(`✅ OK`) + chalk.dim(` (${elapsed}ms)`));
      } else {
        console.log(chalk.red(`❌ Failed`) + chalk.dim(` — ${result.reason}`));
      }
    }

    console.log();

    const available = await getAvailableProviders(config);
    info(`${available.length}/${sorted.length} providers available`);

    if (available.length > 0) {
      success(`Fallback order: ${available.map((p) => p.name).join(" → ")}`);
    } else {
      warn("No providers available. Set API keys and check network.");
    }

    logCommandSuccess("fallback test");
    process.exit(EXIT_SUCCESS);
  });

const resetCommand = new Command("reset")
  .description("Reset rate limit state for all providers")
  .action(async () => {
    logCommandStart("fallback reset");

    const configDir = getConfigDir();
    const limiter = new RateLimiter(configDir);

    const providers = limiter.getAllProviders();
    for (const provider of providers) {
      limiter.reset(provider);
    }

    success(`Rate limit state cleared for ${providers.length} provider(s).`);
    logCommandSuccess("fallback reset");
    process.exit(EXIT_SUCCESS);
  });

// ─── Main Command ────────────────────────────────────────────

export const fallbackCommand = new Command("fallback")
  .description("Manage provider fallback and rate limiting")
  .addCommand(statusCommand)
  .addCommand(testCommand)
  .addCommand(resetCommand);

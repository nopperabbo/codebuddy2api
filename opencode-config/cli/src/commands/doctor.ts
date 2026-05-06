import { Command } from "commander";
import chalk from "chalk";
import { banner, heading, success, warn, error, info } from "../lib/ui.js";
import {
  checkTools,
  checkApiKeys,
  checkConfigFiles,
  checkMcpServers,
  checkLspServers,
  checkInternet,
} from "../lib/checker.js";
import { runAllFixes } from "../lib/fixer.js";
import type { CheckResult, CheckCategory } from "../types.js";
import { EXIT_SUCCESS, EXIT_ERROR, EXIT_WARNING } from "../types.js";

function printResults(results: CheckResult[]): void {
  for (const result of results) {
    switch (result.status) {
      case "pass":
        success(`${result.name} — ${result.message}`);
        break;
      case "warn":
        warn(`${result.name} — ${result.message}`);
        break;
      case "error":
        error(`${result.name} — ${result.message}`);
        break;
    }
  }
}

export const doctorCommand = new Command("doctor")
  .description("Run a full health check of the OpenCode JCE installation")
  .option("--fix", "Automatically fix issues that can be resolved")
  .action(async (opts: { fix?: boolean }) => {
    banner();

    const categories: CheckCategory[] = [];

    // Run all checks
    heading("Tools");
    const toolResults = await checkTools();
    printResults(toolResults);
    categories.push({ name: "Tools", results: toolResults });

    heading("API Keys");
    const apiResults = await checkApiKeys();
    printResults(apiResults);
    categories.push({ name: "API Keys", results: apiResults });

    heading("Configuration Files");
    const configResults = await checkConfigFiles();
    printResults(configResults);
    categories.push({ name: "Config", results: configResults });

    heading("MCP Servers");
    const mcpResults = await checkMcpServers();
    printResults(mcpResults);
    categories.push({ name: "MCP", results: mcpResults });

    heading("LSP Servers");
    const lspResults = await checkLspServers();
    printResults(lspResults);
    categories.push({ name: "LSP", results: lspResults });

    heading("Connectivity");
    const internetResults = await checkInternet();
    printResults(internetResults);
    categories.push({ name: "Internet", results: internetResults });

    // Summary
    const allResults = categories.flatMap((c) => c.results);
    const errors = allResults.filter((r) => r.status === "error").length;
    const warnings = allResults.filter((r) => r.status === "warn").length;
    const passes = allResults.filter((r) => r.status === "pass").length;

    console.log();
    console.log("─".repeat(40));
    console.log(`  Results: ${passes} passed, ${warnings} warnings, ${errors} errors`);
    console.log("─".repeat(40));

    // Auto-fix mode
    if (opts.fix && (errors > 0 || warnings > 0)) {
      console.log();
      heading("Auto-Fix");
      info("Attempting to fix detected issues...");
      console.log();

      const failedChecks = allResults.filter((r) => r.status === "error" || r.status === "warn");
      const fixResults = await runAllFixes(failedChecks);

      if (fixResults.length === 0) {
        info("No auto-fixable issues found. Fix manually using the commands above.");
      } else {
        const fixed = fixResults.filter((r) => r.fixed).length;
        const notFixed = fixResults.filter((r) => !r.fixed).length;

        for (const result of fixResults) {
          if (result.fixed) {
            success(`${result.name} — ${result.message}`);
          } else {
            warn(`${result.name} — ${result.message}`);
          }
        }

        console.log();
        console.log("─".repeat(40));
        console.log(`  Fixed: ${fixed} | Could not fix: ${notFixed}`);
        console.log("─".repeat(40));

        if (fixed > 0) {
          console.log();
          info("Run " + chalk.cyan("opencode-jce doctor") + " again to verify fixes.");
        }
      }

      process.exit(fixResults.some((r) => !r.fixed) ? EXIT_WARNING : EXIT_SUCCESS);
    }

    if (!opts.fix && (errors > 0 || warnings > 0)) {
      console.log();
      info("Run " + chalk.cyan("opencode-jce doctor --fix") + " to auto-fix issues.");
    }

    if (errors > 0) {
      process.exit(EXIT_ERROR);
    } else if (warnings > 0) {
      process.exit(EXIT_WARNING);
    } else {
      process.exit(EXIT_SUCCESS);
    }
  });

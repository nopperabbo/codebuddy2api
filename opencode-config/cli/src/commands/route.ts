import { Command } from "commander";
import chalk from "chalk";
import { analyzeComplexity, routeToProfile } from "../lib/router.js";
import { listProfiles } from "../lib/profiles.js";
import { heading, info, error } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";

export const routeCommand = new Command("route")
  .description("Analyze a prompt and show which profile would be selected")
  .argument("<prompt>", "The prompt/task to analyze")
  .action(async (prompt: string) => {
    logCommandStart("route", { promptLength: prompt.length });

    const profiles = await listProfiles();

    if (profiles.length === 0) {
      error("No profiles found. Run the installer to deploy configuration.");
      logCommandError("route", "No profiles found");
      process.exit(EXIT_ERROR);
    }

    const complexity = analyzeComplexity(prompt);
    const decision = routeToProfile(prompt, profiles);

    heading("Smart Routing Analysis");
    console.log();
    console.log(`  ${chalk.bold("Prompt:")}      ${prompt.length > 60 ? prompt.substring(0, 60) + "..." : prompt}`);
    console.log(`  ${chalk.bold("Length:")}      ${prompt.length} chars`);
    console.log();

    const complexityColors = {
      simple: chalk.green,
      moderate: chalk.yellow,
      complex: chalk.red,
    };
    const colorFn = complexityColors[complexity];
    console.log(`  ${chalk.bold("Complexity:")}  ${colorFn(complexity.toUpperCase())}`);
    console.log(`  ${chalk.bold("Profile:")}     ${chalk.cyan(decision.profile)}`);
    console.log(`  ${chalk.bold("Reason:")}      ${decision.reason}`);
    console.log();

    // Show the selected profile details
    const selectedProfile = profiles.find((p) => p.id === decision.profile);
    if (selectedProfile) {
      info(`Model: ${selectedProfile.provider}/${selectedProfile.model}`);
      info(`Max Tokens: ${selectedProfile.maxTokens}`);
    }

    logCommandSuccess("route", `complexity=${complexity} profile=${decision.profile}`);
    process.exit(EXIT_SUCCESS);
  });

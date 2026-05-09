import { Command } from "commander";
import chalk from "chalk";
import { listProfiles, getActiveProfileId, setActiveProfile } from "../lib/profiles.js";
import { heading, info, success, error } from "../lib/ui.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";

export const useCommand = new Command("use")
  .description("Switch the active model profile")
  .argument("[profile-id]", "Profile ID to switch to")
  .option("-l, --list", "List all available profiles")
  .option("-c, --current", "Show the currently active profile")
  .action(async (profileId: string | undefined, options: { list?: boolean; current?: boolean }) => {
    if (options.list) {
      await showProfileList();
      return;
    }

    if (options.current) {
      await showCurrentProfile();
      return;
    }

    if (!profileId) {
      // No argument and no flag — show help-like output
      await showProfileList();
      return;
    }

    // Switch to the specified profile
    const profile = await setActiveProfile(profileId);

    if (!profile) {
      const profiles = await listProfiles();
      const available = profiles.map((p) => p.id).join(", ");
      error(`Profile not found: "${profileId}"`);
      info(`Available profiles: ${available}`);
      process.exit(EXIT_ERROR);
    }

    success(`Switched to: ${profile.name}`);
    info(`  ${profile.description}`);
    info(`  Provider: ${profile.provider} | Model: ${profile.model}`);
    process.exit(EXIT_SUCCESS);
  });

async function showProfileList(): Promise<void> {
  heading("Available Profiles");

  const profiles = await listProfiles();
  const activeId = await getActiveProfileId();

  if (profiles.length === 0) {
    error("No profiles found. Run the installer to deploy configuration.");
    process.exit(EXIT_ERROR);
  }

  for (const profile of profiles) {
    const isActive = profile.id === activeId;
    const marker = isActive ? chalk.green(" [ACTIVE]") : "";
    const id = chalk.bold(profile.id.padEnd(15));
    console.log(`  ${id}${profile.description}${marker}`);
  }

  console.log();
  info("Usage: opencode-jce use <profile-id>");
  process.exit(EXIT_SUCCESS);
}

async function showCurrentProfile(): Promise<void> {
  const activeId = await getActiveProfileId();

  if (!activeId) {
    info("No active profile set. Use: opencode-jce use <profile-id>");
    process.exit(EXIT_SUCCESS);
  }

  const profiles = await listProfiles();
  const profile = profiles.find((p) => p.id === activeId);

  if (!profile) {
    error(`Active profile "${activeId}" not found in profiles directory.`);
    process.exit(EXIT_ERROR);
  }

  heading("Current Profile");
  console.log(`  ${chalk.bold("ID:")}          ${profile.id}`);
  console.log(`  ${chalk.bold("Name:")}        ${profile.name}`);
  console.log(`  ${chalk.bold("Description:")} ${profile.description}`);
  console.log(`  ${chalk.bold("Provider:")}    ${profile.provider}`);
  console.log(`  ${chalk.bold("Model:")}       ${profile.model}`);
  console.log(`  ${chalk.bold("Max Tokens:")}  ${profile.maxTokens}`);
  console.log(`  ${chalk.bold("Temperature:")} ${profile.temperature}`);
  console.log();
  process.exit(EXIT_SUCCESS);
}

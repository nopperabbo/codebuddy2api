import { Command } from "commander";
import chalk from "chalk";
import { MemoryStore } from "../lib/memory.js";
import { getConfigDir } from "../lib/config.js";
import { heading, info, success, error, warn } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";

// ─── Helpers ─────────────────────────────────────────────────

function getStore(): MemoryStore {
  const configDir = getConfigDir();
  const projectDir = process.cwd();
  return new MemoryStore(configDir, projectDir);
}

function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleDateString() + " " + date.toLocaleTimeString();
}

function validateCategoryOption(category: string | undefined): string | undefined {
  if (!category) return undefined;
  const valid = ["project", "preference", "fact", "context"];
  if (!valid.includes(category)) {
    error(`Invalid memory category: ${category}. Expected one of: ${valid.join(", ")}`);
    process.exit(EXIT_ERROR);
  }
  return category;
}

// ─── Subcommands ─────────────────────────────────────────────

const listCommand = new Command("list")
  .description("List all stored memories")
  .option("-c, --category <category>", "Filter by category (project, preference, fact, context)")
  .action((opts: { category?: string }) => {
    logCommandStart("memory list", { category: opts.category });

    const category = validateCategoryOption(opts.category);
    const store = getStore();
    const entries = store.list(category);

    heading("Stored Memories");
    console.log();

    if (entries.length === 0) {
      info("No memories stored" + (opts.category ? ` for category: ${opts.category}` : "") + ".");
      info("Store a memory with: opencode-jce memory set <key> <value>");
      process.exit(EXIT_SUCCESS);
    }

    for (const entry of entries) {
      const categoryBadge = getCategoryBadge(entry.category);
      console.log(`  ${chalk.bold(entry.key)} ${categoryBadge}`);
      console.log(`    ${chalk.dim("Value:")} ${entry.value}`);
      console.log(`    ${chalk.dim("Updated:")} ${formatDate(entry.updatedAt)}${entry.agent ? ` ${chalk.dim("by")} ${entry.agent}` : ""}`);
      console.log();
    }

    info(`Total: ${entries.length} memor${entries.length === 1 ? "y" : "ies"}`);
    logCommandSuccess("memory list", `count=${entries.length}`);
    process.exit(EXIT_SUCCESS);
  });

const setCommand = new Command("set")
  .description("Store a memory")
  .argument("<key>", "Memory key")
  .argument("<value>", "Memory value")
  .option("-c, --category <category>", "Category (project, preference, fact, context)", "context")
  .option("-a, --agent <agent>", "Agent that stored this memory")
  .action((key: string, value: string, opts: { category: string; agent?: string }) => {
    logCommandStart("memory set", { key, category: opts.category });

    const category = validateCategoryOption(opts.category) || "context";
    const store = getStore();
    store.set(key, value, category, opts.agent);

    success(`Memory stored: ${chalk.bold(key)} = ${value}`);
    logCommandSuccess("memory set", `key=${key}`);
    process.exit(EXIT_SUCCESS);
  });

const getCommand = new Command("get")
  .description("Retrieve a memory by key")
  .argument("<key>", "Memory key to retrieve")
  .action((key: string) => {
    logCommandStart("memory get", { key });

    const store = getStore();
    const entry = store.get(key);

    if (!entry) {
      error(`Memory not found: ${key}`);
      logCommandError("memory get", `key not found: ${key}`);
      process.exit(EXIT_ERROR);
    }

    heading(`Memory: ${entry.key}`);
    console.log();
    console.log(`  ${chalk.bold("Key:")}       ${entry.key}`);
    console.log(`  ${chalk.bold("Value:")}     ${entry.value}`);
    console.log(`  ${chalk.bold("Category:")}  ${getCategoryBadge(entry.category)}`);
    console.log(`  ${chalk.bold("Created:")}   ${formatDate(entry.createdAt)}`);
    console.log(`  ${chalk.bold("Updated:")}   ${formatDate(entry.updatedAt)}`);
    if (entry.agent) {
      console.log(`  ${chalk.bold("Agent:")}     ${entry.agent}`);
    }
    console.log();

    logCommandSuccess("memory get", `key=${key}`);
    process.exit(EXIT_SUCCESS);
  });

const searchCommand = new Command("search")
  .description("Search memories by keyword")
  .argument("<query>", "Search query")
  .action((query: string) => {
    logCommandStart("memory search", { query });

    const store = getStore();
    const results = store.search(query);

    heading(`Search Results for "${query}"`);
    console.log();

    if (results.length === 0) {
      info("No memories match your search.");
      process.exit(EXIT_SUCCESS);
    }

    for (const entry of results) {
      const categoryBadge = getCategoryBadge(entry.category);
      console.log(`  ${chalk.bold(entry.key)} ${categoryBadge}`);
      console.log(`    ${entry.value}`);
      console.log();
    }

    info(`Found ${results.length} result${results.length === 1 ? "" : "s"}`);
    logCommandSuccess("memory search", `query=${query} results=${results.length}`);
    process.exit(EXIT_SUCCESS);
  });

const deleteCommand = new Command("delete")
  .description("Delete a memory by key")
  .argument("<key>", "Memory key to delete")
  .action((key: string) => {
    logCommandStart("memory delete", { key });

    const store = getStore();
    const deleted = store.delete(key);

    if (!deleted) {
      error(`Memory not found: ${key}`);
      logCommandError("memory delete", `key not found: ${key}`);
      process.exit(EXIT_ERROR);
    }

    success(`Memory deleted: ${chalk.bold(key)}`);
    logCommandSuccess("memory delete", `key=${key}`);
    process.exit(EXIT_SUCCESS);
  });

const clearCommand = new Command("clear")
  .description("Clear all memories (use --confirm to skip prompt)")
  .option("--confirm", "Skip confirmation")
  .action((opts: { confirm?: boolean }) => {
    logCommandStart("memory clear");

    if (!opts.confirm) {
      warn("This will delete ALL memories for the current project.");
      warn("Run with --confirm to proceed: opencode-jce memory clear --confirm");
      process.exit(EXIT_ERROR);
    }

    const store = getStore();
    store.clear();

    success("All memories cleared.");
    logCommandSuccess("memory clear");
    process.exit(EXIT_SUCCESS);
  });

// ─── Helpers ─────────────────────────────────────────────────

function getCategoryBadge(category: string): string {
  switch (category) {
    case "project":
      return chalk.bgBlue.white(" project ");
    case "preference":
      return chalk.bgMagenta.white(" preference ");
    case "fact":
      return chalk.bgGreen.white(" fact ");
    case "context":
      return chalk.bgYellow.black(" context ");
    default:
      return chalk.bgGray.white(` ${category} `);
  }
}

// ─── Main Command ────────────────────────────────────────────

export const memoryCommand = new Command("memory")
  .description("Persistent context memory for agents across sessions")
  .addCommand(listCommand)
  .addCommand(setCommand)
  .addCommand(getCommand)
  .addCommand(searchCommand)
  .addCommand(deleteCommand)
  .addCommand(clearCommand);

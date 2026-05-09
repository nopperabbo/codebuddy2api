import { Command } from "commander";
import chalk from "chalk";
import * as readline from "readline";
import { loadAgents, addAgent, removeAgent, findAgent, updateAgent } from "../lib/agents.js";
import { heading, info, success, error } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";
import type { Agent } from "../types.js";

/**
 * Prompt the user for input via readline.
 */
function prompt(question: string, defaultValue?: string): Promise<string> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  const suffix = defaultValue ? ` (${defaultValue})` : "";

  return new Promise((resolve) => {
    rl.question(`  ${chalk.cyan("?")} ${question}${suffix}: `, (answer) => {
      rl.close();
      resolve(answer.trim() || defaultValue || "");
    });
  });
}

/**
 * Interactive wizard to collect agent fields.
 */
async function collectAgentFields(existing?: Agent): Promise<Omit<Agent, "id"> & { id?: string }> {
  const id = existing
    ? existing.id
    : await prompt("Agent ID (lowercase, no spaces)", "");
  const name = await prompt("Agent name", existing?.name);
  const role = await prompt("Role/specialty", existing?.role);
  const systemPrompt = await prompt("System prompt", existing?.systemPrompt);
  const preferredProfile = await prompt("Preferred profile ID", existing?.preferredProfile || "sonnet-4.6");
  const maxTokensStr = await prompt("Max tokens", String(existing?.maxTokens || 4096));
  const toolsStr = await prompt("Tools (comma-separated)", existing?.tools?.join(", ") || "read, grep, bash");

  const maxTokens = parseInt(maxTokensStr, 10) || 4096;
  const tools = toolsStr.split(",").map((t) => t.trim()).filter(Boolean);

  return { id, name, role, systemPrompt, preferredProfile, maxTokens, tools };
}

// ─── Subcommands ─────────────────────────────────────────────

const createCommand = new Command("create")
  .description("Create a new agent via interactive wizard")
  .action(async () => {
    logCommandStart("agent create");

    heading("Create New Agent");
    console.log();

    const fields = await collectAgentFields();

    if (!fields.id) {
      error("Agent ID is required.");
      logCommandError("agent create", "No ID provided");
      process.exit(EXIT_ERROR);
    }

    if (!/^[a-z0-9][a-z0-9-]*$/.test(fields.id)) {
      error("Agent ID must be lowercase alphanumeric with hyphens only (e.g. 'my-agent').");
      logCommandError("agent create", "Invalid ID format");
      process.exit(EXIT_ERROR);
    }

    const agent: Agent = {
      id: fields.id!,
      name: fields.name,
      role: fields.role,
      systemPrompt: fields.systemPrompt,
      preferredProfile: fields.preferredProfile,
      maxTokens: fields.maxTokens,
      tools: fields.tools,
    };

    const added = await addAgent(agent);

    if (!added) {
      error(`Agent with ID "${agent.id}" already exists.`);
      logCommandError("agent create", `Duplicate ID: ${agent.id}`);
      process.exit(EXIT_ERROR);
    }

    console.log();
    success(`Agent "${agent.name}" (${agent.id}) created successfully.`);
    logCommandSuccess("agent create", `id=${agent.id}`);
    process.exit(EXIT_SUCCESS);
  });

const listCommand = new Command("list")
  .description("List all agents with their roles")
  .action(async () => {
    logCommandStart("agent list");

    const agents = await loadAgents();

    heading("Registered Agents");
    console.log();

    if (agents.length === 0) {
      info("No agents configured. Use: opencode-jce agent create");
      process.exit(EXIT_SUCCESS);
    }

    for (const agent of agents) {
      const id = chalk.bold(agent.id.padEnd(18));
      const role = chalk.dim(agent.role);
      console.log(`  ${id}${agent.name.padEnd(22)} ${role}`);
    }

    console.log();
    info(`Total: ${agents.length} agent(s)`);
    logCommandSuccess("agent list", `count=${agents.length}`);
    process.exit(EXIT_SUCCESS);
  });

const removeCommand = new Command("remove")
  .description("Remove an agent by ID")
  .argument("<id>", "Agent ID to remove")
  .action(async (id: string) => {
    logCommandStart("agent remove", { id });

    const removed = await removeAgent(id);

    if (!removed) {
      error(`Agent "${id}" not found.`);
      logCommandError("agent remove", `Not found: ${id}`);
      process.exit(EXIT_ERROR);
    }

    success(`Agent "${id}" removed.`);
    logCommandSuccess("agent remove", `id=${id}`);
    process.exit(EXIT_SUCCESS);
  });

const editCommand = new Command("edit")
  .description("Edit an existing agent (re-prompt for fields)")
  .argument("<id>", "Agent ID to edit")
  .action(async (id: string) => {
    logCommandStart("agent edit", { id });

    const existing = await findAgent(id);

    if (!existing) {
      error(`Agent "${id}" not found.`);
      logCommandError("agent edit", `Not found: ${id}`);
      process.exit(EXIT_ERROR);
    }

    heading(`Edit Agent: ${existing.name}`);
    console.log();
    info("Press Enter to keep current value.");
    console.log();

    const fields = await collectAgentFields(existing);

    const updated = await updateAgent(id, {
      name: fields.name,
      role: fields.role,
      systemPrompt: fields.systemPrompt,
      preferredProfile: fields.preferredProfile,
      maxTokens: fields.maxTokens,
      tools: fields.tools,
    });

    if (!updated) {
      error(`Failed to update agent "${id}".`);
      logCommandError("agent edit", `Update failed: ${id}`);
      process.exit(EXIT_ERROR);
    }

    console.log();
    success(`Agent "${id}" updated successfully.`);
    logCommandSuccess("agent edit", `id=${id}`);
    process.exit(EXIT_SUCCESS);
  });

// ─── Main Command ────────────────────────────────────────────

export const agentCommand = new Command("agent")
  .description("Manage custom agents (create, list, edit, remove)")
  .addCommand(createCommand)
  .addCommand(listCommand)
  .addCommand(removeCommand)
  .addCommand(editCommand);

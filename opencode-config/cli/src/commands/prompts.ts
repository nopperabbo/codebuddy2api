import { Command } from "commander";
import chalk from "chalk";
import { listPromptTemplates, loadPromptTemplate, applyPromptToAgent, resetAgentPrompt } from "../lib/prompts.js";
import { heading, info, success, error } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";

// ─── Subcommands ─────────────────────────────────────────────

const listCommand = new Command("list")
  .description("Show available prompt templates")
  .action(async () => {
    logCommandStart("prompts list");

    const templates = listPromptTemplates();

    heading("Prompt Templates");
    console.log();

    if (templates.length === 0) {
      info("No prompt templates found in config/prompts/");
      info("Add .txt files to your prompts directory to create templates.");
      process.exit(EXIT_SUCCESS);
    }

    for (const name of templates) {
      const content = await loadPromptTemplate(name);
      const preview = content
        ? content.substring(0, 60) + (content.length > 60 ? "..." : "")
        : "";
      console.log(`  ${chalk.bold(name.padEnd(15))} ${chalk.dim(preview)}`);
    }

    console.log();
    info(`Total: ${templates.length} template(s)`);
    info("Usage: opencode-jce prompts apply <template> <agent-id>");
    logCommandSuccess("prompts list", `count=${templates.length}`);
    process.exit(EXIT_SUCCESS);
  });

const applyCommand = new Command("apply")
  .description("Apply a prompt template to an agent")
  .argument("<template>", "Template name (without .txt)")
  .argument("<agent-id>", "Agent ID to apply the template to")
  .action(async (template: string, agentId: string) => {
    logCommandStart("prompts apply", { template, agentId });

    const result = await applyPromptToAgent(template, agentId);

    if (!result.success) {
      error(result.error!);
      logCommandError("prompts apply", result.error!);
      process.exit(EXIT_ERROR);
    }

    success(`Template "${template}" applied to agent "${agentId}".`);
    logCommandSuccess("prompts apply", `template=${template} agent=${agentId}`);
    process.exit(EXIT_SUCCESS);
  });

const resetCommand = new Command("reset")
  .description("Reset an agent to its default system prompt (remove template prefix)")
  .argument("<agent-id>", "Agent ID to reset")
  .action(async (agentId: string) => {
    logCommandStart("prompts reset", { agentId });

    const result = await resetAgentPrompt(agentId);

    if (!result.success) {
      error(result.error!);
      logCommandError("prompts reset", result.error!);
      process.exit(EXIT_ERROR);
    }

    success(`Agent "${agentId}" prompt reset to default.`);
    logCommandSuccess("prompts reset", `agent=${agentId}`);
    process.exit(EXIT_SUCCESS);
  });

// ─── Main Command ────────────────────────────────────────────

export const promptsCommand = new Command("prompts")
  .description("Manage prompt templates (list, apply, reset)")
  .addCommand(listCommand)
  .addCommand(applyCommand)
  .addCommand(resetCommand);

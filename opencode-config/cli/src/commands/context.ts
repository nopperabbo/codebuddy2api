import { Command } from "commander";
import { existsSync } from "fs";
import { readFile, writeFile } from "fs/promises";
import { join } from "path";
import chalk from "chalk";
import { heading, info, success, warn, error } from "../lib/ui.js";
import { logCommandStart, logCommandSuccess, logCommandError } from "../lib/logger.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";
import { CONTEXT_FILENAME, getContextTemplate } from "../lib/context-template.js";
import { parseSessionMeta, isStale } from "../lib/context-session.js";
import { getGitState } from "../lib/context-enrichment.js";

// ─── Helpers ─────────────────────────────────────────────────

function getContextPath(): string {
  return join(process.cwd(), CONTEXT_FILENAME);
}

// ─── Subcommands ─────────────────────────────────────────────

const initCommand = new Command("init")
  .description("Create a .opencode-context.md template in the current project")
  .option("--force", "Overwrite existing file")
  .action(async (opts: { force?: boolean }) => {
    logCommandStart("context init");

    const contextPath = getContextPath();

    if (existsSync(contextPath) && !opts.force) {
      warn(`${CONTEXT_FILENAME} already exists in this directory.`);
      info("Use --force to overwrite, or edit the existing file.");
      process.exit(EXIT_ERROR);
    }

    try {
      await writeFile(contextPath, getContextTemplate(), "utf-8");
    } catch (err: any) {
      error(`Failed to write ${CONTEXT_FILENAME}: ${err.message}`);
      process.exit(EXIT_ERROR);
    }

    success(`Created ${CONTEXT_FILENAME} in ${process.cwd()}`);
    console.log();
    info("The AI will automatically read this file at the start of each session.");
    info("Edit it to add your project's stack, decisions, and current status.");
    console.log();
    info(`Tip: Add ${CONTEXT_FILENAME} to your .gitignore if you don't want to share it,`);
    info("or commit it so your team shares the same context.");

    logCommandSuccess("context init");
    process.exit(EXIT_SUCCESS);
  });

const showCommand = new Command("show")
  .description("Display the current project context")
  .action(async () => {
    logCommandStart("context show");

    const contextPath = getContextPath();

    if (!existsSync(contextPath)) {
      warn(`No ${CONTEXT_FILENAME} found in ${process.cwd()}`);
      info(`Run ${chalk.cyan("opencode-jce context init")} to create one.`);
      process.exit(EXIT_ERROR);
    }

    let content: string;
    try {
      content = await readFile(contextPath, "utf-8");
    } catch (err: any) {
      error(`Cannot read ${CONTEXT_FILENAME}: ${err.message}`);
      process.exit(EXIT_ERROR);
    }

    heading("Project Context");
    console.log();
    console.log(content);

    // Show stats
    const lines = content.split("\n").filter((l) => l.trim()).length;
    const estimatedTokens = Math.ceil(content.length / 4); // rough estimate
    console.log();
    info(`File: ${contextPath}`);
    info(`Lines: ${lines} | Estimated tokens: ~${estimatedTokens}`);

    if (estimatedTokens > 800) {
      warn("Context file is getting large. Consider trimming completed tasks.");
    }

    logCommandSuccess("context show", `lines=${lines} tokens=~${estimatedTokens}`);
    process.exit(EXIT_SUCCESS);
  });

const clearCommand = new Command("clear")
  .description("Reset context file to empty template")
  .option("--confirm", "Skip confirmation")
  .action(async (opts: { confirm?: boolean }) => {
    logCommandStart("context clear");

    const contextPath = getContextPath();

    if (!existsSync(contextPath)) {
      warn(`No ${CONTEXT_FILENAME} found. Nothing to clear.`);
      process.exit(EXIT_ERROR);
    }

    if (!opts.confirm) {
      warn("This will reset your context file to the default template.");
      warn(`Run with --confirm to proceed: ${chalk.cyan("opencode-jce context clear --confirm")}`);
      process.exit(EXIT_ERROR);
    }

    try {
      await writeFile(contextPath, getContextTemplate(), "utf-8");
      success("Context file cleared and reset to template.");
    } catch (err: any) {
      error(`Failed to clear context file: ${err.message}`);
      process.exit(EXIT_ERROR);
    }

    logCommandSuccess("context clear");
    process.exit(EXIT_SUCCESS);
  });

const statusCommand = new Command("status")
  .description("Show context health and suggestions")
  .action(async () => {
    logCommandStart("context status");

    const contextPath = getContextPath();

    heading("Context Preservation Status");
    console.log();

    // Check if context file exists
    if (!existsSync(contextPath)) {
      console.log(`  ${chalk.red("✗")} ${CONTEXT_FILENAME} — not found`);
      console.log();
      info(`Create one with: ${chalk.cyan("opencode-jce context init")}`);
      process.exit(EXIT_SUCCESS);
    }

    let content: string;
    try {
      content = await readFile(contextPath, "utf-8");
    } catch (err: any) {
      error(`Cannot read ${CONTEXT_FILENAME}: ${err.message}`);
      process.exit(EXIT_ERROR);
    }
    const lines = content.split("\n");
    const nonEmptyLines = lines.filter((l) => l.trim()).length;
    const estimatedTokens = Math.ceil(content.length / 4);

    // File exists
    console.log(`  ${chalk.green("✓")} ${CONTEXT_FILENAME} — found`);
    console.log(`  ${chalk.green("✓")} Lines: ${nonEmptyLines}`);
    console.log(`  ${chalk.green("✓")} Estimated tokens: ~${estimatedTokens}`);

    // Check sections
    const hasStack = content.includes("## Stack");
    const hasDecisions = content.includes("## Architecture Decisions");
    const hasStatus = content.includes("## Current Status");
    const hasConventions = content.includes("## Conventions");
    const hasNotes = content.includes("## Important Notes");

    console.log();
    console.log("  Sections:");
    console.log(`    ${hasStack ? chalk.green("✓") : chalk.yellow("○")} Stack`);
    console.log(`    ${hasDecisions ? chalk.green("✓") : chalk.yellow("○")} Architecture Decisions`);
    console.log(`    ${hasConventions ? chalk.green("✓") : chalk.yellow("○")} Conventions`);
    console.log(`    ${hasStatus ? chalk.green("✓") : chalk.yellow("○")} Current Status`);
    console.log(`    ${hasNotes ? chalk.green("✓") : chalk.yellow("○")} Important Notes`);

    // Suggestions
    console.log();
    if (estimatedTokens > 800) {
      warn("File is large (>800 tokens). Consider removing completed tasks.");
    } else if (estimatedTokens < 50) {
      info("File is very short. Add more context for better AI continuity.");
    } else {
      success("Context file is well-sized for efficient token usage.");
    }

    // Check last updated
    const lastUpdatedMatch = content.match(/Last updated: (\d{4}-\d{2}-\d{2})/);
    if (lastUpdatedMatch) {
      const lastDate = new Date(lastUpdatedMatch[1]);
      const daysSince = Math.floor((Date.now() - lastDate.getTime()) / (1000 * 60 * 60 * 24));
      if (daysSince > 7) {
        warn(`Last updated ${daysSince} days ago. Consider reviewing if it's still accurate.`);
      }
    }

    logCommandSuccess("context status");
    process.exit(EXIT_SUCCESS);
  });

const auditCommand = new Command("audit")
  .description("Check context file compliance and report issues")
  .action(async () => {
    logCommandStart("context audit");

    const contextPath = getContextPath();
    const issues: string[] = [];
    const suggestions: string[] = [];

    // 1. Check if context file exists
    if (!existsSync(contextPath)) {
      error(`${CONTEXT_FILENAME} not found in ${process.cwd()}`);
      info(`Run ${chalk.cyan("opencode-jce context init")} to create one.`);
      logCommandError("context audit", "context file not found");
      process.exit(EXIT_ERROR);
    }

    // 2. Read the file content
    let content: string;
    try {
      content = await readFile(contextPath, "utf-8");
    } catch (err: any) {
      error(`Cannot read ${CONTEXT_FILENAME}: ${err.message}`);
      logCommandError("context audit", err.message);
      process.exit(EXIT_ERROR);
    }

    heading("Context Compliance Audit");
    console.log();

    // 3. Check session metadata
    const meta = parseSessionMeta(content);
    if (!meta) {
      issues.push("No session metadata found — file has never been tracked by the AI");
      suggestions.push("Start an AI session so the context file gets session metadata injected");
    } else {
      // 4. Check staleness
      if (isStale(meta)) {
        issues.push(
          `Context is stale — last session: ${meta.lastSession}, sessions without update: ${meta.sessionsWithoutUpdate ?? "unknown"}`,
        );
        suggestions.push("Review and update the context file to reflect current project state");
      }
    }

    // 5. Check git state
    const git = await getGitState(process.cwd());
    if (git) {
      if (git.uncommittedCount > 10) {
        issues.push(`${git.uncommittedCount} uncommitted files — context may be out of sync`);
        suggestions.push("Commit or stash changes, then update context to match current state");
      }
    } else {
      suggestions.push("Not a git repository — git-based checks skipped");
    }

    // 6. Check section completeness
    const requiredSections = [
      { name: "Stack", heading: "## Stack" },
      { name: "Architecture Decisions", heading: "## Architecture Decisions" },
      { name: "Conventions", heading: "## Conventions" },
      { name: "Current Status", heading: "## Current Status" },
      { name: "Important Notes", heading: "## Important Notes" },
    ];

    const missingSections: string[] = [];
    for (const section of requiredSections) {
      if (!content.includes(section.heading)) {
        missingSections.push(section.name);
      }
    }

    if (missingSections.length > 0) {
      issues.push(`Missing sections: ${missingSections.join(", ")}`);
      suggestions.push("Add the missing sections to ensure full context coverage");
    }

    // 7. Check for placeholder content
    const placeholders = [
      "auto-detect from project files",
      "(none yet)",
      "(session start)",
    ];
    const foundPlaceholders: string[] = [];
    for (const placeholder of placeholders) {
      if (content.includes(placeholder)) {
        foundPlaceholders.push(`"${placeholder}"`);
      }
    }

    if (foundPlaceholders.length > 0) {
      issues.push(`Placeholder content still present: ${foundPlaceholders.join(", ")}`);
      suggestions.push("Replace placeholder text with actual project information");
    }

    // 8. Check file size
    const lines = content.split("\n").filter((l) => l.trim()).length;
    if (lines > 50) {
      issues.push(`File has ${lines} non-empty lines — exceeds recommended 40-line limit`);
      suggestions.push("Prune completed tasks and archive old decisions to keep the file concise");
    }

    // ─── Report ────────────────────────────────────────────────
    if (issues.length === 0) {
      success("Context compliance: HEALTHY");
    } else {
      warn(`Context compliance: ${issues.length} issue(s) found`);
      for (const issue of issues) {
        console.log(`  ${chalk.red("✗")} ${issue}`);
      }
    }

    if (suggestions.length > 0) {
      console.log();
      info("Suggestions:");
      for (const suggestion of suggestions) {
        console.log(`  ${chalk.blue("→")} ${suggestion}`);
      }
    }

    logCommandSuccess("context audit", `issues=${issues.length}`);
    process.exit(EXIT_SUCCESS);
  });

// ─── Main Command ────────────────────────────────────────────

export const contextCommand = new Command("context")
  .description("Manage project context for AI session continuity")
  .addCommand(initCommand)
  .addCommand(showCommand)
  .addCommand(clearCommand)
  .addCommand(statusCommand)
  .addCommand(auditCommand);

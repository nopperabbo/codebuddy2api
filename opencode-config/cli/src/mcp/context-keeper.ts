#!/usr/bin/env bun
/**
 * context-keeper — MCP Server for automatic context preservation.
 *
 * Provides tools that the AI MUST call at specific points:
 *   - context_read:       Read .opencode-context.md (call at session start)
 *   - context_update:     Update specific sections (call after completing tasks)
 *   - context_checkpoint: Validate & prune the file (call before session ends)
 *
 * This turns "remember to edit a file" into explicit tool calls,
 * which AI models follow far more reliably than free-form instructions.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { readFile, writeFile, stat } from "fs/promises";
import { join } from "path";
import { z } from "zod";
import {
  CONTEXT_FILENAME,
  ARCHIVE_FILENAME,
  MAX_LINES_TARGET,
  MAX_LINES_HARD,
  getContextTemplate,
} from "../lib/context-template.js";
import {
  parseSessionMeta,
  formatSessionMeta,
  incrementSession,
  markUpdated,
  isStale,
  computeContentHash,
} from "../lib/context-session.js";
import { smartPrune } from "../lib/context-similarity.js";
import { enrichContext } from "../lib/context-enrichment.js";
import {
  parseRelatedProjects,
  readRelatedContext,
  formatRelatedSummary,
} from "../lib/context-cross-project.js";

// ─── Re-export section utilities (extracted to prevent circular deps) ────
export { countLines, getSection, replaceSection } from "../lib/context-sections.js";
import { countLines, getSection, replaceSection } from "../lib/context-sections.js";

// ─── Helpers (exported for testing) ──────────────────────────

export function getProjectRoot(): string {
  return process.env.PROJECT_ROOT || process.cwd();
}

function contextPath(): string {
  return join(getProjectRoot(), CONTEXT_FILENAME);
}

function archivePath(): string {
  return join(getProjectRoot(), ARCHIVE_FILENAME);
}

async function fileExists(path: string): Promise<boolean> {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

async function readContext(): Promise<string | null> {
  try {
    return await readFile(contextPath(), "utf-8");
  } catch {
    return null;
  }
}

async function writeContext(content: string): Promise<void> {
  // Update the "Last updated" line
  const today = new Date().toISOString().split("T")[0];
  const updated = content.replace(
    /> Last updated:.*/,
    `> Last updated: ${today}`
  );
  await writeFile(contextPath(), updated, "utf-8");
}

/**
 * Remove completed tasks ([x]) from ## Current Status,
 * and resolved/completed items from ## Important Notes.
 *
 * Important Notes items are pruned if they:
 *   - Start with "- [x]" (completed checkbox)
 *   - Start with "- [RESOLVED]" (explicitly marked resolved)
 */
export function pruneCompleted(content: string): string {
  const lines = content.split("\n");
  const result: string[] = [];
  let currentSection = "";

  for (const line of lines) {
    if (line.startsWith("## ")) {
      currentSection = line;
      result.push(line);
      continue;
    }

    // Prune [x] items from Current Status
    if (
      currentSection.startsWith("## Current Status") &&
      /^\s*-\s*\[x\]/i.test(line)
    ) {
      continue;
    }

    // Prune [x] and [RESOLVED] items from Important Notes
    if (
      currentSection.startsWith("## Important Notes") &&
      /^\s*-\s*(\[x\]|\[RESOLVED\])/i.test(line)
    ) {
      continue;
    }

    result.push(line);
  }

  return result.join("\n");
}



export interface ContextArchiveResult {
  content: string;
  archiveAppend: string;
  actions: string[];
}

export function pruneAndArchiveContext(content: string, today = new Date().toISOString().split("T")[0]): ContextArchiveResult {
  const actions: string[] = [];
  let updated = pruneCompleted(content);
  if (updated !== content) {
    actions.push("Pruned completed/resolved items from Current Status and Important Notes");
  }

  let archiveAppend = "";
  if (countLines(updated) > MAX_LINES_HARD) {
    const archDecisions = getSection(updated, "Architecture Decisions");
    const impNotes = getSection(updated, "Important Notes");

    if (archDecisions.length > 3 || impNotes.length > 3) {
      archiveAppend += `## Archived: ${today}\n`;

      if (archDecisions.length > 3) {
        const toArchive = archDecisions.slice(0, -3);
        const toKeep = archDecisions.slice(-3);
        archiveAppend += `### Architecture Decisions\n${toArchive.join("\n")}\n\n`;
        updated = replaceSection(updated, "Architecture Decisions", toKeep);
        actions.push(`Archived ${toArchive.length} old architecture decisions`);
      }

      if (impNotes.length > 3) {
        const toArchive = impNotes.slice(0, -3);
        const toKeep = impNotes.slice(-3);
        archiveAppend += `### Important Notes\n${toArchive.join("\n")}\n\n`;
        updated = replaceSection(updated, "Important Notes", toKeep);
        actions.push(`Archived ${toArchive.length} old important notes`);
      }

      if (!updated.includes("see .opencode-context-archive.md")) {
        updated = updated.replace(
          /^> Auto-maintained by AI\..*$/m,
          "> Auto-maintained by AI. You can edit this file freely.\n> Archived entries: see .opencode-context-archive.md"
        );
      }
    }
  }

  return { content: updated, archiveAppend, actions };
}

async function appendArchive(content: string): Promise<void> {
  if (!content) return;

  let archiveContent = "";
  if (await fileExists(archivePath())) {
    archiveContent = await readFile(archivePath(), "utf-8");
    archiveContent += "\n";
  } else {
    archiveContent = `# Context Archive\n> Historical decisions and notes. Reference only.\n\n`;
  }
  archiveContent += content;
  await writeFile(archivePath(), archiveContent, "utf-8");
}

// ─── MCP Server ──────────────────────────────────────────────

const server = new McpServer(
  {
    name: "context-keeper",
    version: "1.9.1",
  },
  {
    instructions: [
      "MANDATORY: Call context_read at the START of every session.",
      "Call context_update after completing any task or making architecture decisions.",
      "Call context_checkpoint before the session ends or before committing.",
    ].join(" "),
  }
);

// ─── Tool: context_read ──────────────────────────────────────

server.tool(
  "context_read",
  "Read .opencode-context.md at session start. Creates the file if it doesn't exist. Returns the current context.",
  {},
  async () => {
    const existing = await readContext();

    if (existing) {
      const actions: string[] = [];

      // 1. Increment session counter
      let content = incrementSession(existing);
      actions.push("Incremented session counter");

      // 2. Structural prune (completed/resolved items + archive)
      const pruned = pruneAndArchiveContext(content);
      if (pruned.content !== content) {
        await appendArchive(pruned.archiveAppend);
        actions.push(...pruned.actions);
      }
      content = pruned.content;

      // 3. Smart prune (dedup + resolved-note detection)
      const smart = smartPrune(content);
      if (smart.actions.length > 0) {
        content = smart.prunedContent;
        actions.push(...smart.actions);
      }

      // 4. Update content hash
      const hash = computeContentHash(content);
      const meta = parseSessionMeta(content);
      if (meta) {
        meta.contentHash = hash;
        meta.lastPrune = new Date().toISOString().split("T")[0];
        const metaLine = formatSessionMeta(meta);
        content = content.replace(/^<!-- session: .+ -->$/m, metaLine);
      }

      // 5. Write updated content
      await writeContext(content);

      // 6. Get enrichment data (git state, deps)
      const projectRoot = getProjectRoot();
      const enrichment = await enrichContext(projectRoot);

      // 7. Get related project summaries
      const relatedProjects = parseRelatedProjects(content);
      let relatedSummary = "";
      if (relatedProjects.length > 0) {
        const relatedContexts = await readRelatedContext(projectRoot, relatedProjects);
        relatedSummary = formatRelatedSummary(relatedContexts);
      }

      // 8. Check staleness
      const sessionMeta = parseSessionMeta(content);
      let stalenessWarning = "";
      if (sessionMeta && isStale(sessionMeta)) {
        stalenessWarning = `\nSTALENESS WARNING: Context may be outdated (${sessionMeta.sessionsWithoutUpdate ?? 0} sessions without update, last session: ${sessionMeta.lastSession}). Review and update all sections.`;
      }

      const lines = countLines(content);
      const sessionInfo = sessionMeta
        ? `Session #${sessionMeta.count}`
        : "Session #1";

      const responseParts: string[] = [
        `--- .opencode-context.md (${lines} lines) — ${sessionInfo} ---`,
        content,
        "---",
      ];

      // Auto-maintenance actions
      if (actions.length > 0) {
        responseParts.push("Auto-maintenance:");
        for (const a of actions) {
          responseParts.push(`  - ${a}`);
        }
      }

      // Enrichment data
      if (enrichment) {
        responseParts.push("");
        responseParts.push("Project State:");
        responseParts.push(enrichment);
      }

      // Related project summaries
      if (relatedSummary) {
        responseParts.push("");
        responseParts.push(relatedSummary);
      }

      // Staleness warning
      if (stalenessWarning) {
        responseParts.push(stalenessWarning);
      }

      // Line count warning
      responseParts.push(
        lines > MAX_LINES_TARGET
          ? `WARNING: File has ${lines} lines (target: ${MAX_LINES_TARGET}). Consider archiving old entries.`
          : `File size OK (${lines}/${MAX_LINES_TARGET} target lines).`
      );

      // Reminders
      responseParts.push("");
      responseParts.push("REMINDER: You MUST call context_update after completing any task.");
      responseParts.push("REMINDER: You MUST call context_checkpoint before the session ends or before committing.");
      responseParts.push("Failure to do so will result in lost context for the next session.");

      return {
        content: [
          {
            type: "text" as const,
            text: responseParts.join("\n"),
          },
        ],
      };
    }

    // Create new file from template
    await writeContext(getContextTemplate());
    return {
      content: [
        {
          type: "text" as const,
          text: `Created new ${CONTEXT_FILENAME} from template. Please auto-detect the project stack and update the ## Stack section.`,
        },
      ],
    };
  }
);

// ─── Tool: context_update ────────────────────────────────────

server.tool(
  "context_update",
  "Update a specific section of .opencode-context.md. Use after completing tasks, making decisions, or adding dependencies.",
  {
    section: z
      .enum([
        "Stack",
        "Architecture Decisions",
        "Conventions",
        "Current Status",
        "Important Notes",
        "Related Projects",
      ])
      .describe("Which section to update"),
    action: z
      .enum(["add", "replace"])
      .describe(
        "add = append lines to section, replace = replace entire section content"
      ),
    lines: z
      .array(z.string().max(200))
      .min(1)
      .max(20)
      .describe(
        'Lines to add/replace. Use "- [x] task" for completed, "- [ ] task" for pending.'
      ),
  },
  async ({ section, action, lines: rawLines }) => {
    // Sanitize: strip lines that could corrupt section structure
    const lines = rawLines
      .map((l) => (l.startsWith("## ") ? `- ${l.slice(3)}` : l))
      .map((l) => l.replace(/\r?\n/g, " ")); // no embedded newlines

    let content = await readContext();

    if (!content) {
      // Auto-create if missing
      content = getContextTemplate();
    }

    let updated: string;

    if (action === "replace") {
      updated = replaceSection(content, section, lines);
    } else {
      // Add: append to existing section
      const existing = getSection(content, section);
      // Deduplicate: don't add lines that already exist
      const newLines = lines.filter(
        (l) => !existing.some((e) => e.trim() === l.trim())
      );
      if (newLines.length === 0) {
        return {
          content: [
            {
              type: "text" as const,
              text: `No new lines to add — all entries already exist in ## ${section}.`,
            },
          ],
        };
      }
      updated = replaceSection(content, section, [...existing, ...newLines]);
    }

    // Mark session as updated (reset sessionsWithoutUpdate)
    updated = markUpdated(updated);

    // Update content hash
    const hash = computeContentHash(updated);
    const meta = parseSessionMeta(updated);
    if (meta) {
      meta.contentHash = hash;
      const metaLine = formatSessionMeta(meta);
      updated = updated.replace(/^<!-- session: .+ -->$/m, metaLine);
    }

    await writeContext(updated);

    const lineCount = countLines(updated);
    const warning =
      lineCount > MAX_LINES_HARD
        ? `\nWARNING: File now has ${lineCount} lines (hard limit: ${MAX_LINES_HARD}). Call context_checkpoint to auto-archive.`
        : "";

    return {
      content: [
        {
          type: "text" as const,
          text: `Updated ## ${section} (${action}). File: ${lineCount} lines.${warning}\nREMINDER: Call context_checkpoint before session ends or before committing.`,
        },
      ],
    };
  }
);

// ─── Tool: context_checkpoint ────────────────────────────────

server.tool(
  "context_checkpoint",
  "Validate, prune, and optionally archive .opencode-context.md. Call before session ends or before committing.",
  {},
  async () => {
    let content = await readContext();

    if (!content) {
      return {
        content: [
          {
            type: "text" as const,
            text: `No ${CONTEXT_FILENAME} found. Nothing to checkpoint.`,
          },
        ],
      };
    }

    const pruned = pruneAndArchiveContext(content);
    const actions: string[] = [...pruned.actions];
    content = pruned.content;
    await appendArchive(pruned.archiveAppend);

    await writeContext(content);

    const finalLines = countLines(content);
    actions.push(`Final file: ${finalLines} lines`);

    return {
      content: [
        {
          type: "text" as const,
          text: [
            "Checkpoint complete:",
            ...actions.map((a) => `  - ${a}`),
            "",
            finalLines > MAX_LINES_TARGET
              ? `Note: File still above target (${finalLines}/${MAX_LINES_TARGET}). Consider manually trimming verbose entries.`
              : "File size is within target.",
          ].join("\n"),
        },
      ],
    };
  }
);

// ─── Tool: context_history ───────────────────────────────────

server.tool(
  "context_history",
  "Show session stats, staleness status, and section sizes for the context file.",
  {},
  async () => {
    const content = await readContext();

    if (!content) {
      return {
        content: [
          {
            type: "text" as const,
            text: `No ${CONTEXT_FILENAME} found. Call context_read first.`,
          },
        ],
      };
    }

    const lines = countLines(content);
    const meta = parseSessionMeta(content);

    const responseParts: string[] = [
      `File: ${CONTEXT_FILENAME} (${lines} lines)`,
      "",
    ];

    // Session stats
    if (meta) {
      responseParts.push("Session Stats:");
      responseParts.push(`  - Session count: ${meta.count}`);
      responseParts.push(`  - Last session: ${meta.lastSession}`);
      responseParts.push(`  - Last update: ${meta.lastUpdate ?? "never"}`);
      responseParts.push(`  - Sessions without update: ${meta.sessionsWithoutUpdate ?? 0}`);
      responseParts.push(`  - Last prune: ${meta.lastPrune ?? "never"}`);
      responseParts.push(`  - Content hash: ${meta.contentHash ?? "none"}`);
      responseParts.push("");

      // Staleness status
      const stale = isStale(meta);
      responseParts.push(`Staleness: ${stale ? "STALE — review and update all sections" : "OK"}`);
    } else {
      responseParts.push("Session Stats: No session metadata found (file predates v2).");
    }

    // Section sizes
    responseParts.push("");
    responseParts.push("Section Sizes:");
    const sections = [
      "Stack",
      "Architecture Decisions",
      "Conventions",
      "Current Status",
      "Important Notes",
      "Related Projects",
    ];
    for (const section of sections) {
      const entries = getSection(content, section);
      if (entries.length > 0) {
        responseParts.push(`  - ${section}: ${entries.length} entries`);
      }
    }

    return {
      content: [
        {
          type: "text" as const,
          text: responseParts.join("\n"),
        },
      ],
    };
  }
);

// ─── Tool: context_query_related ─────────────────────────────

server.tool(
  "context_query_related",
  "Query context from related projects defined in the Related Projects section.",
  {
    project: z
      .string()
      .optional()
      .describe("Filter to a specific related project path. If omitted, returns all."),
  },
  async ({ project }) => {
    const content = await readContext();

    if (!content) {
      return {
        content: [
          {
            type: "text" as const,
            text: `No ${CONTEXT_FILENAME} found. Call context_read first.`,
          },
        ],
      };
    }

    let related = parseRelatedProjects(content);

    if (related.length === 0) {
      return {
        content: [
          {
            type: "text" as const,
            text: `No related projects found in ## Related Projects section. Add entries like: - ../other-project: "Description"`,
          },
        ],
      };
    }

    // Filter to specific project if requested
    if (project) {
      related = related.filter(
        (r) => r.path === project || r.path.includes(project)
      );
      if (related.length === 0) {
        return {
          content: [
            {
              type: "text" as const,
              text: `No related project matching "${project}" found.`,
            },
          ],
        };
      }
    }

    const projectRoot = getProjectRoot();
    const contexts = await readRelatedContext(projectRoot, related);

    if (contexts.length === 0) {
      return {
        content: [
          {
            type: "text" as const,
            text: `Found ${related.length} related project(s) but none have a ${CONTEXT_FILENAME} file.`,
          },
        ],
      };
    }

    const summary = formatRelatedSummary(contexts);

    return {
      content: [
        {
          type: "text" as const,
          text: summary || "No context data available from related projects.",
        },
      ],
    };
  }
);

// ─── Start ───────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

if (import.meta.main) {
  main().catch((err) => {
    console.error("context-keeper failed to start:", err);
    process.exit(1);
  });
}

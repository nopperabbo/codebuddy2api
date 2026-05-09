/**
 * context-cross-project — Read and summarize context files from related projects.
 *
 * Useful for monorepos and microservice architectures where multiple
 * projects share context and need awareness of each other's state.
 */

import { resolve, basename } from "path";
import { readFile } from "fs/promises";
import { getSection } from "./context-sections.js";
import { CONTEXT_FILENAME } from "./context-template.js";

/**
 * A related project reference parsed from the context file.
 */
export interface RelatedProject {
  path: string;
  description: string;
}

/**
 * Extracted context from a related project's context file.
 */
export interface RelatedContext {
  path: string;
  stack: string[];
  status: string[];
  decisions: string[];
}

/**
 * Parse the `## Related Projects` section from context content.
 * Expected format: `- <relative-path>: "<description>"`
 *
 * @returns Array of related projects, or empty array if section missing.
 */
export function parseRelatedProjects(content: string): RelatedProject[] {
  const lines = getSection(content, "Related Projects");
  if (lines.length === 0) return [];

  const projects: RelatedProject[] = [];
  const pattern = /^-\s+(.+?):\s+"(.+)"$/;

  for (const line of lines) {
    const match = line.match(pattern);
    if (match) {
      projects.push({
        path: match[1],
        description: match[2],
      });
    }
  }

  return projects;
}

/**
 * Read `.opencode-context.md` from each related project and extract
 * Stack, Current Status, and Architecture Decisions sections.
 *
 * Skips projects whose context file doesn't exist (no error thrown).
 */
export async function readRelatedContext(
  projectRoot: string,
  related: RelatedProject[]
): Promise<RelatedContext[]> {
  const results: RelatedContext[] = [];

  for (const project of related) {
    const contextPath = resolve(projectRoot, project.path, CONTEXT_FILENAME);
    try {
      const content = await readFile(contextPath, "utf-8");
      results.push({
        path: project.path,
        stack: getSection(content, "Stack"),
        status: getSection(content, "Current Status"),
        decisions: getSection(content, "Architecture Decisions"),
      });
    } catch {
      // Skip projects whose context file doesn't exist
      continue;
    }
  }

  return results;
}

/**
 * Format related project contexts as a concise read-only summary.
 *
 * - Uses basename of path as project name
 * - Limits active status items to 3
 * - Excludes completed `[x]` items from status
 *
 * @returns Formatted summary string, or empty string for empty array.
 */
export function formatRelatedSummary(contexts: RelatedContext[]): string {
  if (contexts.length === 0) return "";

  const lines: string[] = ["## Related Project Summaries (read-only)"];

  for (const ctx of contexts) {
    const name = basename(ctx.path);
    lines.push(`### ${name} (${ctx.path})`);

    // Stack: join items, strip leading "- "
    if (ctx.stack.length > 0) {
      const stackItems = ctx.stack.map((s) => s.replace(/^-\s*/, "")).join(", ");
      lines.push(`  Stack: ${stackItems}`);
    }

    // Active status: exclude [x] items, limit to 3
    const activeStatus = ctx.status
      .filter((s) => !s.includes("[x]"))
      .slice(0, 3);
    if (activeStatus.length > 0) {
      lines.push(`  Active: ${activeStatus.join("; ")}`);
    }

    // Decisions
    if (ctx.decisions.length > 0) {
      const decisionItems = ctx.decisions
        .map((d) => d.replace(/^-\s*/, ""))
        .join("; ");
      lines.push(`  Decisions: ${decisionItems}`);
    }
  }

  return lines.join("\n");
}

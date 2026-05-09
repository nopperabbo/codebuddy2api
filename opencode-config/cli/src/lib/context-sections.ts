/**
 * context-sections — Shared section-manipulation utilities.
 *
 * Extracted from context-keeper.ts so that other modules
 * (context-lock, context-similarity, context-cross-project)
 * can import them without creating circular dependencies.
 */

/**
 * Count non-empty lines in content.
 */
export function countLines(content: string): number {
  return content.split("\n").filter((l) => l.trim().length > 0).length;
}

/**
 * Extract a section's content by heading name.
 */
export function getSection(content: string, heading: string): string[] {
  const lines = content.split("\n");
  const result: string[] = [];
  let inSection = false;

  for (const line of lines) {
    if (line.startsWith(`## ${heading}`)) {
      inSection = true;
      continue;
    }
    if (line.startsWith("## ") && inSection) {
      break;
    }
    if (inSection) {
      result.push(line);
    }
  }

  return result.filter((l) => l.trim().length > 0);
}

/**
 * Replace a section's content by heading name.
 */
export function replaceSection(
  content: string,
  heading: string,
  newLines: string[]
): string {
  const lines = content.split("\n");
  const result: string[] = [];
  let inSection = false;
  let sectionReplaced = false;

  for (const line of lines) {
    if (line.startsWith(`## ${heading}`)) {
      inSection = true;
      sectionReplaced = true;
      result.push(line);
      for (const nl of newLines) {
        result.push(nl);
      }
      continue;
    }
    if (line.startsWith("## ") && inSection) {
      inSection = false;
      result.push(""); // Preserve blank separator line
    }
    if (!inSection) {
      result.push(line);
    }
  }

  // Ensure trailing newline after last section if it was replaced
  if (inSection && sectionReplaced) {
    result.push(""); // Ensure trailing newline after last section
  }

  // If section didn't exist, append it
  if (!sectionReplaced) {
    result.push("");
    result.push(`## ${heading}`);
    for (const nl of newLines) {
      result.push(nl);
    }
  }

  return result.join("\n");
}

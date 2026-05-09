/**
 * Shared context file template and constants.
 * Used by both the MCP server (context-keeper) and the CLI (context command).
 */

export const CONTEXT_FILENAME = ".opencode-context.md";
export const ARCHIVE_FILENAME = ".opencode-context-archive.md";
export const MAX_LINES_TARGET = 40;
export const MAX_LINES_HARD = 50;
export const MAX_STALENESS_DAYS = 7;
export const MAX_SESSIONS_WITHOUT_UPDATE = 5;

/**
 * Generate the context template with today's date.
 * Called at runtime (not module load) to ensure correct date.
 */
export function getContextTemplate(): string {
  const today = new Date().toISOString().split("T")[0];
  return `# Project Context
> Auto-maintained by AI. You can edit this file freely.
> Last updated: ${today}

## Stack
- (auto-detect from project files)

## Architecture Decisions
- (none yet)

## Conventions
- (none yet)

## Current Status
- [ ] (session start)

## Important Notes
- (none yet)

## Related Projects
- (none — add related projects as: - <path>: "<description>")
`;
}

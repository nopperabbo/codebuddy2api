/**
 * context-lock — Optimistic concurrency with content-hash conflict detection
 * and section-level three-way merge.
 */

import { getSection, replaceSection } from "./context-sections.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ConflictResult {
  hasConflict: boolean;
}

// ---------------------------------------------------------------------------
// Conflict detection
// ---------------------------------------------------------------------------

/**
 * Compare an expected hash against the current file hash.
 *
 * - Returns no conflict when hashes match.
 * - Returns conflict when hashes differ.
 * - Returns no conflict when `expectedHash` is undefined (first write).
 */
export function detectConflict(
  expectedHash: string | undefined,
  currentHash: string,
): ConflictResult {
  if (expectedHash === undefined) {
    return { hasConflict: false };
  }
  return { hasConflict: expectedHash !== currentHash };
}

// ---------------------------------------------------------------------------
// Three-way section-level merge
// ---------------------------------------------------------------------------

const SECTIONS = [
  "Stack",
  "Architecture Decisions",
  "Conventions",
  "Current Status",
  "Important Notes",
] as const;

/**
 * Three-way merge at section level.
 *
 * Strategy: start with `theirs` (the file currently on disk), then for each
 * known section add lines that are in `ours` but not in `base` (our
 * additions), skipping any that already exist in `theirs` (dedup).
 */
export function mergeContexts(
  base: string,
  ours: string,
  theirs: string,
): string {
  let merged = theirs;

  for (const section of SECTIONS) {
    const baseLines = getSection(base, section);
    const ourLines = getSection(ours, section);
    const theirLines = getSection(merged, section);

    // Lines we added (present in ours, absent from base)
    const baseSet = new Set(baseLines.map((l) => l.trim()));
    const ourAdditions = ourLines.filter((l) => !baseSet.has(l.trim()));

    // Deduplicate against theirs
    const theirSet = new Set(theirLines.map((l) => l.trim()));
    const newAdditions = ourAdditions.filter((l) => !theirSet.has(l.trim()));

    if (newAdditions.length > 0) {
      const mergedLines = [...theirLines, ...newAdditions];
      merged = replaceSection(merged, section, mergedLines);
    }
  }

  return merged;
}

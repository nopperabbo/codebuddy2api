/**
 * context-similarity — Fuzzy deduplication & smart pruning for context files.
 *
 * Provides Jaccard similarity for detecting near-duplicate lines,
 * resolved-note detection, and a smartPrune function that cleans
 * Architecture Decisions and Important Notes sections.
 */

import { getSection, replaceSection } from "./context-sections.js";

// ---------------------------------------------------------------------------
// Jaccard similarity
// ---------------------------------------------------------------------------

/**
 * Word-level Jaccard similarity (case-insensitive).
 *
 * Splits on whitespace, creates sets, computes |intersection| / |union|.
 * Two empty strings → 1.0. One empty, one not → 0.0.
 */
export function jaccardSimilarity(a: string, b: string): number {
  const setA = new Set(a.toLowerCase().split(/\s+/).filter(Boolean));
  const setB = new Set(b.toLowerCase().split(/\s+/).filter(Boolean));

  if (setA.size === 0 && setB.size === 0) return 1.0;
  if (setA.size === 0 || setB.size === 0) return 0.0;

  let intersection = 0;
  for (const word of setA) {
    if (setB.has(word)) intersection++;
  }

  const union = new Set([...setA, ...setB]).size;
  return intersection / union;
}

// ---------------------------------------------------------------------------
// Duplicate detection
// ---------------------------------------------------------------------------

export interface DuplicatePair {
  kept: string;
  removed: string;
  similarity: number;
}

/** Common stop words stripped before duplicate comparison. */
const STOP_WORDS = new Set([
  "a", "an", "the", "is", "are", "was", "were", "be", "been",
  "for", "of", "to", "in", "on", "at", "by", "with", "as",
  "and", "or", "but", "not", "it", "its", "this", "that",
  "use", "using", "used",
]);

/**
 * Normalise a context line for comparison: strip bullet prefix,
 * remove stop words, lowercase.
 */
function normaliseLine(line: string): string {
  const stripped = line.replace(/^-\s*/, "");
  return stripped
    .toLowerCase()
    .split(/\s+/)
    .filter((w) => w.length > 0 && !STOP_WORDS.has(w))
    .join(" ");
}

/**
 * Find near-duplicate lines using Jaccard similarity.
 *
 * Compares all pairs (after normalising); keeps first occurrence,
 * marks later as duplicate. Tracks removed indices to avoid double-counting.
 */
export function findDuplicates(
  lines: string[],
  threshold: number = 0.6
): DuplicatePair[] {
  const normalised = lines.map(normaliseLine);
  const removed = new Set<number>();
  const result: DuplicatePair[] = [];

  for (let i = 0; i < lines.length; i++) {
    if (removed.has(i)) continue;
    for (let j = i + 1; j < lines.length; j++) {
      if (removed.has(j)) continue;
      const sim = jaccardSimilarity(normalised[i], normalised[j]);
      if (sim >= threshold) {
        result.push({ kept: lines[i], removed: lines[j], similarity: sim });
        removed.add(j);
      }
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Resolved-note detection
// ---------------------------------------------------------------------------

const RESOLVED_KEYWORDS = [
  "fixed",
  "resolved",
  "completed",
  "done",
  "finished",
  "merged",
  "deployed",
  "closed",
];

const RESOLVED_PATTERNS = RESOLVED_KEYWORDS.map(
  (kw) => new RegExp(`\\b${kw}\\b`, "i")
);

/**
 * Return lines that contain resolved-state keywords (case-insensitive,
 * word-boundary matched).
 */
export function detectResolvedNotes(lines: string[]): string[] {
  return lines.filter((line) =>
    RESOLVED_PATTERNS.some((re) => re.test(line))
  );
}

// ---------------------------------------------------------------------------
// Smart prune
// ---------------------------------------------------------------------------

export interface SmartPruneResult {
  prunedContent: string;
  actions: string[];
}

/**
 * Smart-prune a context file:
 * 1. Deduplicate "Architecture Decisions" (threshold 0.6)
 * 2. Detect & remove resolved notes in "Important Notes" (without [x] marker)
 * 3. Deduplicate "Important Notes" (threshold 0.6)
 * 4. Replace empty sections with `["- (none yet)"]`
 */
export function smartPrune(content: string): SmartPruneResult {
  const actions: string[] = [];
  let result = content;

  // --- Architecture Decisions: dedup ---
  const archLines = getSection(result, "Architecture Decisions");
  if (archLines.length > 0) {
    const archDupes = findDuplicates(archLines, 0.6);
    if (archDupes.length > 0) {
      const removedSet = new Set(archDupes.map((d) => d.removed));
      const pruned = archLines.filter((l) => !removedSet.has(l));
      const finalLines = pruned.length > 0 ? pruned : ["- (none yet)"];
      result = replaceSection(result, "Architecture Decisions", finalLines);
      for (const d of archDupes) {
        actions.push(
          `Removed duplicate from Architecture Decisions: "${d.removed}" (similarity ${d.similarity.toFixed(2)} with "${d.kept}")`
        );
      }
    }
  }

  // --- Important Notes: resolved detection + dedup ---
  let noteLines = getSection(result, "Important Notes");
  if (noteLines.length > 0) {
    // Detect resolved notes (only lines without [x] marker — those are tasks)
    const resolvedLines = detectResolvedNotes(
      noteLines.filter((l) => !l.includes("[x]"))
    );
    if (resolvedLines.length > 0) {
      const resolvedSet = new Set(resolvedLines);
      noteLines = noteLines.filter((l) => !resolvedSet.has(l));
      for (const r of resolvedLines) {
        actions.push(`Removed resolved note: "${r}"`);
      }
    }

    // Dedup remaining
    const noteDupes = findDuplicates(noteLines, 0.6);
    if (noteDupes.length > 0) {
      const removedSet = new Set(noteDupes.map((d) => d.removed));
      noteLines = noteLines.filter((l) => !removedSet.has(l));
      for (const d of noteDupes) {
        actions.push(
          `Removed duplicate from Important Notes: "${d.removed}" (similarity ${d.similarity.toFixed(2)} with "${d.kept}")`
        );
      }
    }

    const finalNotes = noteLines.length > 0 ? noteLines : ["- (none yet)"];
    result = replaceSection(result, "Important Notes", finalNotes);
  }

  return { prunedContent: result, actions };
}

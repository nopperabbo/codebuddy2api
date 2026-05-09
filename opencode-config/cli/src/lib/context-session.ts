/**
 * context-session — Multi-session awareness with metadata tracking.
 *
 * Stores session metadata as an HTML comment in the context file,
 * invisible in rendered markdown but parseable by code.
 *
 * Format:
 * <!-- session: <ISO timestamp> | count: <N> | last-prune: <date> | ... -->
 */

import {
  MAX_STALENESS_DAYS,
  MAX_SESSIONS_WITHOUT_UPDATE,
} from "./context-template.js";

// ─── Interfaces ──────────────────────────────────────────────

export interface SessionMeta {
  lastSession: string; // ISO timestamp
  count: number; // total session count
  lastPrune?: string; // date of last prune
  lastUpdate?: string; // ISO timestamp of last context_update call
  contentHash?: string; // hash for optimistic concurrency
  sessionsWithoutUpdate?: number; // sessions since last meaningful update
}

export interface StalenessConfig {
  maxAgeDays?: number; // default: 7
  maxSessionsWithoutUpdate?: number; // default: 5
}

// ─── Regex ───────────────────────────────────────────────────

const META_REGEX = /^<!-- session: .+ -->$/m;

// ─── parseSessionMeta ────────────────────────────────────────

/**
 * Parse the HTML comment metadata from context file content.
 * Returns null if no metadata comment is found.
 */
export function parseSessionMeta(content: string): SessionMeta | null {
  const match = content.match(META_REGEX);
  if (!match) return null;

  const line = match[0];
  // Extract the inner content between <!-- and -->
  const inner = line.slice(5, -4).trim(); // strip "<!-- " and " -->"

  const parts = inner.split("|").map((p) => p.trim());
  const map = new Map<string, string>();

  for (const part of parts) {
    const colonIdx = part.indexOf(":");
    if (colonIdx === -1) continue;
    const key = part.slice(0, colonIdx).trim();
    const value = part.slice(colonIdx + 1).trim();
    map.set(key, value);
  }

  const sessionVal = map.get("session");
  const countVal = map.get("count");

  if (!sessionVal || !countVal) return null;

  const meta: SessionMeta = {
    lastSession: sessionVal,
    count: parseInt(countVal, 10),
  };

  const lastPrune = map.get("last-prune");
  if (lastPrune) meta.lastPrune = lastPrune;

  const lastUpdate = map.get("last-update");
  if (lastUpdate) meta.lastUpdate = lastUpdate;

  const contentHash = map.get("content-hash");
  if (contentHash) meta.contentHash = contentHash;

  const staleSessions = map.get("stale-sessions");
  if (staleSessions) meta.sessionsWithoutUpdate = parseInt(staleSessions, 10);

  return meta;
}

// ─── formatSessionMeta ───────────────────────────────────────

/**
 * Format a SessionMeta object as an HTML comment string.
 */
export function formatSessionMeta(meta: SessionMeta): string {
  const parts: string[] = [
    `session: ${meta.lastSession}`,
    `count: ${meta.count}`,
  ];

  if (meta.lastPrune !== undefined) {
    parts.push(`last-prune: ${meta.lastPrune}`);
  }
  if (meta.lastUpdate !== undefined) {
    parts.push(`last-update: ${meta.lastUpdate}`);
  }
  if (meta.contentHash !== undefined) {
    parts.push(`content-hash: ${meta.contentHash}`);
  }
  if (meta.sessionsWithoutUpdate !== undefined) {
    parts.push(`stale-sessions: ${meta.sessionsWithoutUpdate}`);
  }

  return `<!-- ${parts.join(" | ")} -->`;
}

// ─── incrementSession ────────────────────────────────────────

/**
 * Increment session count, update timestamp, insert metadata if missing.
 * Also increments sessionsWithoutUpdate.
 */
export function incrementSession(content: string): string {
  const now = new Date().toISOString();
  const existing = parseSessionMeta(content);

  if (existing) {
    const updated: SessionMeta = {
      ...existing,
      lastSession: now,
      count: existing.count + 1,
      sessionsWithoutUpdate: (existing.sessionsWithoutUpdate ?? 0) + 1,
    };
    const newLine = formatSessionMeta(updated);
    return content.replace(META_REGEX, newLine);
  }

  // No existing metadata — insert after first line
  const lines = content.split("\n");
  const newMeta: SessionMeta = {
    lastSession: now,
    count: 1,
    sessionsWithoutUpdate: 1,
  };
  const metaLine = formatSessionMeta(newMeta);
  lines.splice(1, 0, metaLine);
  return lines.join("\n");
}

// ─── markUpdated ─────────────────────────────────────────────

/**
 * Set lastUpdate to now and reset sessionsWithoutUpdate to 0.
 * Inserts metadata if none exists.
 */
export function markUpdated(content: string): string {
  const now = new Date().toISOString();
  const existing = parseSessionMeta(content);

  if (existing) {
    const updated: SessionMeta = {
      ...existing,
      lastUpdate: now,
      sessionsWithoutUpdate: 0,
    };
    const newLine = formatSessionMeta(updated);
    return content.replace(META_REGEX, newLine);
  }

  // No existing metadata — insert after first line with initial values
  const lines = content.split("\n");
  const newMeta: SessionMeta = {
    lastSession: now,
    count: 1,
    lastUpdate: now,
    sessionsWithoutUpdate: 0,
  };
  const metaLine = formatSessionMeta(newMeta);
  lines.splice(1, 0, metaLine);
  return lines.join("\n");
}

// ─── isStale ─────────────────────────────────────────────────

/**
 * Check if context is stale based on time and session-based criteria.
 */
export function isStale(meta: SessionMeta, config?: StalenessConfig): boolean {
  const maxAge = config?.maxAgeDays ?? MAX_STALENESS_DAYS;
  const maxSessions = config?.maxSessionsWithoutUpdate ?? MAX_SESSIONS_WITHOUT_UPDATE;

  // Time-based staleness
  const lastSessionTime = new Date(meta.lastSession).getTime();
  const now = Date.now();
  const daysSinceLastSession = (now - lastSessionTime) / (1000 * 60 * 60 * 24);
  if (daysSinceLastSession > maxAge) return true;

  // Session-based staleness
  if (
    meta.sessionsWithoutUpdate !== undefined &&
    meta.sessionsWithoutUpdate > maxSessions
  ) {
    return true;
  }

  return false;
}

// ─── computeContentHash ──────────────────────────────────────

/**
 * Compute MD5 hash (first 8 chars) of content excluding the metadata line.
 */
export function computeContentHash(content: string): string {
  // Strip the metadata line (and its trailing newline) before hashing
  const stripped = content.replace(/^<!-- session: .+ -->\n?/m, "");
  const hasher = new Bun.CryptoHasher("md5");
  hasher.update(stripped);
  return hasher.digest("hex").slice(0, 8);
}

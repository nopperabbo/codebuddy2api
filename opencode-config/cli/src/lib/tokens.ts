import { join } from "path";
import { existsSync } from "fs";
import { homedir, platform } from "os";
import { Database } from "bun:sqlite";

// ─── Types ───────────────────────────────────────────────────

/**
 * Legacy compatibility type — used by analytics.ts and optimizer.ts.
 */
export interface TokenUsageEntry {
  timestamp: string;
  provider: string;
  model: string;
  agent: string;
  inputTokens: number;
  outputTokens: number;
  cost: number;
}

export interface TokenData {
  input: number;
  output: number;
  reasoning: number;
  cache: {
    read: number;
    write: number;
  };
}

export interface MessageTokenInfo {
  timestamp: number;
  provider: string;
  model: string;
  agent: string;
  role: string;
  tokens: TokenData;
  cost: number;
}

export interface TokenSummary {
  totalMessages: number;
  totalSessions: number;
  tokens: {
    input: number;
    output: number;
    reasoning: number;
    cacheRead: number;
    cacheWrite: number;
    total: number;
  };
  totalCost: number;
  byProvider: Record<string, { tokens: number; cost: number; messages: number }>;
  byModel: Record<string, { tokens: number; cost: number; messages: number }>;
}

// ─── DB Location Detection ───────────────────────────────────

/**
 * Detect the OpenCode database path across platforms.
 * OpenCode uses XDG_DATA_HOME on Linux, ~/Library/Application Support on macOS,
 * and ~/.local/share on Windows (via Git Bash / Bun).
 */
export function detectOpenCodeDB(): string | null {
  const os = platform();
  const home = homedir();

  const candidates: string[] = [];

  if (os === "win32") {
    // Windows: OpenCode uses ~/.local/share/opencode/
    candidates.push(join(home, ".local", "share", "opencode", "opencode.db"));
    // Also check LOCALAPPDATA
    if (process.env.LOCALAPPDATA) {
      candidates.push(join(process.env.LOCALAPPDATA, "opencode", "opencode.db"));
    }
    // Also check APPDATA
    if (process.env.APPDATA) {
      candidates.push(join(process.env.APPDATA, "opencode", "opencode.db"));
    }
  } else if (os === "darwin") {
    // macOS
    candidates.push(join(home, "Library", "Application Support", "opencode", "opencode.db"));
    candidates.push(join(home, ".local", "share", "opencode", "opencode.db"));
  } else {
    // Linux
    const xdgData = process.env.XDG_DATA_HOME || join(home, ".local", "share");
    candidates.push(join(xdgData, "opencode", "opencode.db"));
  }

  for (const path of candidates) {
    if (existsSync(path)) {
      return path;
    }
  }

  return null;
}

// ─── Token Tracker (SQLite) ──────────────────────────────────

export class TokenTracker {
  private dbPath: string;

  /**
   * Create a TokenTracker.
   * @param pathOrConfigDir - Either a direct path to opencode.db, or a config directory
   *                          (legacy usage — will auto-detect the DB).
   */
  constructor(pathOrConfigDir?: string) {
    if (pathOrConfigDir && pathOrConfigDir.endsWith(".db")) {
      this.dbPath = pathOrConfigDir;
    } else {
      // Auto-detect DB location
      const detected = detectOpenCodeDB();
      if (!detected) {
        throw new Error("OpenCode database not found.");
      }
      this.dbPath = detected;
    }
  }

  /**
   * Open the database in readonly mode to avoid conflicts with running OpenCode.
   */
  private openDB(): Database {
    try {
      return new Database(this.dbPath, { readonly: true });
    } catch (err: any) {
      if (err?.code === "SQLITE_CANTOPEN") {
        throw new Error(
          "Cannot open OpenCode database. Make sure OpenCode is not exclusively locking it."
        );
      }
      throw err;
    }
  }

  /**
   * Validate that the database has the expected schema.
   */
  validateSchema(): boolean {
    const db = this.openDB();
    try {
      const tables = db
        .query("SELECT name FROM sqlite_master WHERE type='table'")
        .all() as { name: string }[];
      const tableNames = tables.map((t) => t.name);
      return tableNames.includes("message") && tableNames.includes("session");
    } finally {
      db.close();
    }
  }

  /**
   * Get the full token usage summary from all messages.
   */
  getSummary(): TokenSummary {
    const db = this.openDB();

    try {
      // Count sessions
      const sessionCount = db.query("SELECT COUNT(*) as cnt FROM session").get() as {
        cnt: number;
      };

      // Get all messages with data
      const rows = db
        .query("SELECT time_created, data FROM message ORDER BY time_created ASC")
        .all() as { time_created: number; data: string }[];

      const summary: TokenSummary = {
        totalMessages: 0,
        totalSessions: sessionCount.cnt,
        tokens: {
          input: 0,
          output: 0,
          reasoning: 0,
          cacheRead: 0,
          cacheWrite: 0,
          total: 0,
        },
        totalCost: 0,
        byProvider: {},
        byModel: {},
      };

      for (const row of rows) {
        let data: any;
        try {
          data = JSON.parse(row.data);
        } catch {
          continue; // skip malformed entries
        }

        // Only count messages that have token data
        if (!data.tokens) continue;

        const tokens = data.tokens;
        const input = tokens.input || 0;
        const output = tokens.output || 0;
        const reasoning = tokens.reasoning || 0;
        const cacheRead = tokens.cache?.read || 0;
        const cacheWrite = tokens.cache?.write || 0;
        const msgTotal = input + output + reasoning;

        // Skip zero-token messages (e.g. user messages)
        if (msgTotal === 0 && reasoning === 0) continue;

        summary.totalMessages++;
        summary.tokens.input += input;
        summary.tokens.output += output;
        summary.tokens.reasoning += reasoning;
        summary.tokens.cacheRead += cacheRead;
        summary.tokens.cacheWrite += cacheWrite;

        const cost = data.cost || 0;
        summary.totalCost += cost;

        // By provider
        const provider = data.providerID || "unknown";
        if (!summary.byProvider[provider]) {
          summary.byProvider[provider] = { tokens: 0, cost: 0, messages: 0 };
        }
        summary.byProvider[provider].tokens += msgTotal;
        summary.byProvider[provider].cost += cost;
        summary.byProvider[provider].messages++;

        // By model
        const model = data.modelID || "unknown";
        if (!summary.byModel[model]) {
          summary.byModel[model] = { tokens: 0, cost: 0, messages: 0 };
        }
        summary.byModel[model].tokens += msgTotal;
        summary.byModel[model].cost += cost;
        summary.byModel[model].messages++;
      }

      summary.tokens.total =
        summary.tokens.input + summary.tokens.output + summary.tokens.reasoning;

      return summary;
    } finally {
      db.close();
    }
  }

  // ─── Legacy Compatibility Methods ────────────────────────
  // Used by dashboard.ts, optimize.ts, analytics.ts

  /**
   * Convert DB messages to legacy TokenUsageEntry format, filtered by time.
   */
  private queryEntries(since?: Date): TokenUsageEntry[] {
    const db = this.openDB();
    try {
      let rows: { time_created: number; data: string }[];

      if (since) {
        const sinceMs = since.getTime();
        rows = db
          .query("SELECT time_created, data FROM message WHERE time_created >= ? ORDER BY time_created ASC")
          .all(sinceMs) as any[];
      } else {
        rows = db
          .query("SELECT time_created, data FROM message ORDER BY time_created ASC")
          .all() as any[];
      }

      const entries: TokenUsageEntry[] = [];

      for (const row of rows) {
        let data: any;
        try {
          data = JSON.parse(row.data);
        } catch {
          continue;
        }

        if (!data.tokens) continue;
        const input = data.tokens.input || 0;
        const output = data.tokens.output || 0;
        const reasoning = data.tokens.reasoning || 0;
        if (input === 0 && output === 0 && reasoning === 0) continue;

        // Normalize timestamp: if value looks like seconds (< 1e12), convert to ms
        const timeMs = row.time_created < 1e12 ? row.time_created * 1000 : row.time_created;

        entries.push({
          timestamp: new Date(timeMs).toISOString(),
          provider: data.providerID || "unknown",
          model: data.modelID || "unknown",
          agent: data.agent || "default",
          inputTokens: input,
          outputTokens: output,
          cost: data.cost || 0,
        });
      }

      return entries;
    } finally {
      db.close();
    }
  }

  /** Get all entries for today. */
  getToday(): TokenUsageEntry[] {
    const now = new Date();
    const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return this.queryEntries(startOfDay);
  }

  /** Get all entries for the last 7 days. */
  getThisWeek(): TokenUsageEntry[] {
    const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    return this.queryEntries(weekAgo);
  }

  /** Get all entries for the current month. */
  getThisMonth(): TokenUsageEntry[] {
    const now = new Date();
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    return this.queryEntries(startOfMonth);
  }

  /** Get all entries without a time filter. */
  getAll(): TokenUsageEntry[] {
    return this.queryEntries();
  }

  /** Calculate total cost from entries. */
  getTotalCost(entries: TokenUsageEntry[]): number {
    return entries.reduce((sum, e) => sum + e.cost, 0);
  }
}

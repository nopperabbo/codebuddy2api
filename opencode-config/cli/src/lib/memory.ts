import { join } from "path";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "fs";
import { createHash, randomBytes } from "crypto";

// ─── Types ───────────────────────────────────────────────────

export interface MemoryEntry {
  id: string;
  key: string;
  value: string;
  category: "project" | "preference" | "fact" | "context";
  createdAt: string;
  updatedAt: string;
  agent?: string;
}

interface MemoryFile {
  entries: MemoryEntry[];
}

// ─── Constants ───────────────────────────────────────────────

const MEMORY_DIR = "memory";
const GLOBAL_FILE = "global.json";

// ─── Memory Store Class ──────────────────────────────────────

export class MemoryStore {
  private configDir: string;
  private memoryDir: string;
  private projectHash: string;

  constructor(configDir: string, projectDir?: string) {
    this.configDir = configDir;
    this.memoryDir = join(configDir, MEMORY_DIR);
    this.projectHash = projectDir
      ? createHash("sha256").update(projectDir).digest("hex").slice(0, 12)
      : "global";
  }

  /**
   * Ensure the memory directory exists.
   */
  private ensureMemoryDir(): void {
    if (!existsSync(this.memoryDir)) {
      mkdirSync(this.memoryDir, { recursive: true });
    }
  }

  /**
   * Get the file path for the current project's memory.
   */
  private getFilePath(): string {
    if (this.projectHash === "global") {
      return join(this.memoryDir, GLOBAL_FILE);
    }
    return join(this.memoryDir, `${this.projectHash}.json`);
  }

  /**
   * Get the global memory file path.
   */
  private getGlobalFilePath(): string {
    return join(this.memoryDir, GLOBAL_FILE);
  }

  /**
   * Load entries from a memory file.
   */
  private loadFile(filePath: string): MemoryEntry[] {
    if (!existsSync(filePath)) {
      return [];
    }

    const content = readFileSync(filePath, "utf-8");
    try {
      const data = JSON.parse(content) as MemoryFile;
      return data.entries || [];
    } catch {
      // Backup corrupted file before returning empty
      const backupPath = filePath + ".corrupted";
      if (!existsSync(backupPath)) {
        writeFileSync(backupPath, content, "utf-8");
      }
      return [];
    }
  }

  /**
   * Save entries to a memory file.
   */
  private saveFile(filePath: string, entries: MemoryEntry[]): void {
    this.ensureMemoryDir();
    const data: MemoryFile = { entries };
    const tmpPath = filePath + ".tmp";
    writeFileSync(tmpPath, JSON.stringify(data, null, 2), "utf-8");
    renameSync(tmpPath, filePath);
  }

  /**
   * Load all entries for the current project.
   */
  private loadEntries(): MemoryEntry[] {
    return this.loadFile(this.getFilePath());
  }

  /**
   * Save all entries for the current project.
   */
  private saveEntries(entries: MemoryEntry[]): void {
    this.saveFile(this.getFilePath(), entries);
  }

  /**
   * Generate a unique ID for a memory entry.
   */
  private generateId(): string {
    return randomBytes(8).toString("hex");
  }

  /**
   * Store a memory (creates or updates).
   */
  set(key: string, value: string, category: string, agent?: string): void {
    const entries = this.loadEntries();
    const now = new Date().toISOString();
    const validCategory = this.validateCategory(category);

    const existingIndex = entries.findIndex((e) => e.key === key);

    if (existingIndex >= 0) {
      // Update existing entry
      entries[existingIndex].value = value;
      entries[existingIndex].category = validCategory;
      entries[existingIndex].updatedAt = now;
      if (agent) entries[existingIndex].agent = agent;
    } else {
      // Create new entry
      const entry: MemoryEntry = {
        id: this.generateId(),
        key,
        value,
        category: validCategory,
        createdAt: now,
        updatedAt: now,
        agent,
      };
      entries.push(entry);
    }

    this.saveEntries(entries);
  }

  /**
   * Retrieve a memory by key.
   */
  get(key: string): MemoryEntry | null {
    const entries = this.loadEntries();
    return entries.find((e) => e.key === key) || null;
  }

  /**
   * Search memories by keyword (searches key and value).
   */
  search(query: string): MemoryEntry[] {
    const entries = this.loadEntries();
    const lowerQuery = query.toLowerCase();

    return entries.filter(
      (e) =>
        e.key.toLowerCase().includes(lowerQuery) ||
        e.value.toLowerCase().includes(lowerQuery)
    );
  }

  /**
   * List all memories, optionally filtered by category.
   */
  list(category?: string): MemoryEntry[] {
    const entries = this.loadEntries();

    if (category) {
      const validCategory = this.validateCategory(category);
      return entries.filter((e) => e.category === validCategory);
    }

    return entries;
  }

  /**
   * Delete a memory by key.
   */
  delete(key: string): boolean {
    const entries = this.loadEntries();
    const initialLength = entries.length;
    const filtered = entries.filter((e) => e.key !== key);

    if (filtered.length === initialLength) {
      return false; // Key not found
    }

    this.saveEntries(filtered);
    return true;
  }

  /**
   * Clear all memories for the current project.
   */
  clear(): void {
    this.saveEntries([]);
  }

  /**
   * Get context for current project (all project-scoped memories).
   */
  getProjectContext(): MemoryEntry[] {
    return this.loadEntries();
  }

  /**
   * Validate and normalize category string.
   */
  private validateCategory(category: string): "project" | "preference" | "fact" | "context" {
    const valid = ["project", "preference", "fact", "context"];
    if (valid.includes(category)) {
      return category as "project" | "preference" | "fact" | "context";
    }
    throw new Error(`Invalid memory category: ${category}. Expected one of: ${valid.join(", ")}`);
  }
}

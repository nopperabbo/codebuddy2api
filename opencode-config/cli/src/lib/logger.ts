import { join } from "path";
import { existsSync, statSync, renameSync, appendFileSync, mkdirSync } from "fs";
import { getConfigDir } from "./config.js";

const MAX_LOG_SIZE = 1024 * 1024; // 1MB

export type LogLevel = "INFO" | "WARN" | "ERROR" | "DEBUG";

/**
 * Get the path to the logs directory.
 */
export function getLogsDir(): string {
  return join(getConfigDir(), "logs");
}

/**
 * Get the path to the main log file.
 */
export function getLogFilePath(): string {
  return join(getLogsDir(), "opencode-jce.log");
}

/**
 * Ensure the logs directory exists.
 */
function ensureLogsDir(): void {
  const logsDir = getLogsDir();
  if (!existsSync(logsDir)) {
    mkdirSync(logsDir, { recursive: true });
  }
}

/**
 * Rotate the log file if it exceeds MAX_LOG_SIZE.
 * Renames current log to .log.1 and starts fresh.
 */
function rotateIfNeeded(): void {
  const logPath = getLogFilePath();

  if (!existsSync(logPath)) {
    return;
  }

  const stats = statSync(logPath);
  if (stats.size >= MAX_LOG_SIZE) {
    const rotatedPath = logPath + ".1";
    // Overwrite any existing rotated file
    renameSync(logPath, rotatedPath);
  }
}

/**
 * Format a log entry.
 */
function formatEntry(level: LogLevel, command: string, message: string): string {
  const timestamp = new Date().toISOString();
  return `[${timestamp}] [${level}] command=${command} ${message}\n`;
}

/**
 * Write a log entry to the log file.
 */
export function log(level: LogLevel, command: string, message: string): void {
  try {
    ensureLogsDir();
    rotateIfNeeded();

    const entry = formatEntry(level, command, message);
    appendFileSync(getLogFilePath(), entry, "utf-8");
  } catch {
    // Logging should never crash the CLI
  }
}

/**
 * Log a command execution start.
 */
export function logCommandStart(command: string, args?: Record<string, unknown>): void {
  const argsStr = args ? ` args=${JSON.stringify(args)}` : "";
  log("INFO", command, `started${argsStr}`);
}

/**
 * Log a command execution success.
 */
export function logCommandSuccess(command: string, details?: string): void {
  const detailStr = details ? ` details=${details}` : "";
  log("INFO", command, `result=success${detailStr}`);
}

/**
 * Log a command execution failure.
 */
export function logCommandError(command: string, error: string): void {
  log("ERROR", command, `result=error error=${error}`);
}

/**
 * Log a warning during command execution.
 */
export function logCommandWarn(command: string, message: string): void {
  log("WARN", command, message);
}

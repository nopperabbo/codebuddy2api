// ─── Config Types ────────────────────────────────────────────

export interface Agent {
  id: string;
  name: string;
  role: string;
  systemPrompt: string;
  preferredProfile: string;
  maxTokens: number;
  tools: string[];
  workflow?: string[];
  outputFormat?: string;
  contextRules?: Record<string, string>;
  verification?: string[];
}

export interface AgentsConfig {
  agents: Agent[];
}

export interface TokenSaving {
  contextTruncation: boolean;
  maxContextMessages: number;
  aggressiveSummarization?: boolean;
  skipSystemPromptRepetition?: boolean;
}

export interface Profile {
  id: string;
  name: string;
  description: string;
  provider: "openai" | "anthropic" | "ollama" | "auto" | "google" | "deepseek" | "xai" | "mistral";
  model: string;
  maxTokens: number;
  temperature: number;
  apiKeyEnv: string;
  tokenSaving: TokenSaving;
}

export interface McpServer {
  command: string;
  args: string[];
  env?: Record<string, string>;
  description?: string;
}

export interface McpConfig {
  mcpServers: Record<string, McpServer>;
}

export interface LspEntry {
  server: string;
  command: string;
  args: string[];
  filetypes: string[];
  installCommand: string;
}

export interface LspConfig {
  lsp: Record<string, LspEntry>;
}

export interface ActiveProfile {
  activeProfile: string;
  switchedAt: string;
}

// ─── Doctor Types ────────────────────────────────────────────

export type CheckStatus = "pass" | "warn" | "error";

export interface CheckResult {
  name: string;
  status: CheckStatus;
  message: string;
}

export interface CheckCategory {
  name: string;
  results: CheckResult[];
}

// ─── Exit Codes ──────────────────────────────────────────────

export const EXIT_SUCCESS = 0;
export const EXIT_ERROR = 1;
export const EXIT_WARNING = 2;

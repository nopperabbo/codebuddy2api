import { join } from "path";
import { existsSync } from "fs";
import { readFile } from "fs/promises";

// ─── Types ───────────────────────────────────────────────────

export interface ProviderConfig {
  name: string;
  apiKeyEnv: string;
  healthEndpoint: string;
  priority: number;
}

export interface FallbackConfig {
  providers: ProviderConfig[];
  maxRetries: number;
  timeoutMs: number;
}

export interface ProviderHealthResult {
  provider: ProviderConfig;
  healthy: boolean;
  reason?: string;
}

const TRUSTED_PROVIDER_ENDPOINTS: Record<string, string[]> = {
  anthropic: ["https://api.anthropic.com/v1/messages"],
  openai: ["https://api.openai.com/v1/models"],
  ollama: ["http://localhost:11434/api/tags", "http://127.0.0.1:11434/api/tags"],
};

function isLocalEndpoint(url: URL): boolean {
  return ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
}

function validateFallbackConfig(config: FallbackConfig): FallbackConfig {
  if (!Array.isArray(config.providers)) {
    throw new Error("Invalid fallback config: providers must be an array");
  }
  if (!Number.isFinite(config.maxRetries) || config.maxRetries < 0) {
    throw new Error("Invalid fallback config: maxRetries must be a non-negative number");
  }
  if (!Number.isFinite(config.timeoutMs) || config.timeoutMs <= 0) {
    throw new Error("Invalid fallback config: timeoutMs must be a positive number");
  }

  for (const provider of config.providers) {
    if (!provider.name || !provider.apiKeyEnv || !provider.healthEndpoint) {
      throw new Error("Invalid fallback config: provider is missing required fields");
    }

    let endpoint: URL;
    try {
      endpoint = new URL(provider.healthEndpoint);
    } catch {
      throw new Error(`Invalid fallback healthEndpoint for ${provider.name}`);
    }

    const trustedEndpoints = TRUSTED_PROVIDER_ENDPOINTS[provider.name];
    const isTrusted = trustedEndpoints?.includes(provider.healthEndpoint) ?? false;
    const isTrustedLocal = provider.name === "ollama" && isLocalEndpoint(endpoint);
    if (!isTrusted && !isTrustedLocal) {
      throw new Error(`Untrusted fallback healthEndpoint for ${provider.name}: ${provider.healthEndpoint}`);
    }
    if (!isLocalEndpoint(endpoint) && endpoint.protocol !== "https:") {
      throw new Error(`Untrusted fallback healthEndpoint for ${provider.name}: HTTPS is required`);
    }
  }

  return config;
}

function parseFallbackJson(content: string, filePath: string): FallbackConfig {
  try {
    return JSON.parse(content) as FallbackConfig;
  } catch {
    throw new Error(`Failed to parse ${filePath}: invalid JSON`);
  }
}

// ─── Config Loading ──────────────────────────────────────────

/**
 * Load fallback configuration from the given config directory.
 * Falls back to bundled config/fallback.json if not found in user config.
 */
export async function loadFallbackConfig(configDir: string): Promise<FallbackConfig> {
  const userPath = join(configDir, "fallback.json");

  if (existsSync(userPath)) {
    const content = await readFile(userPath, "utf-8");
    return validateFallbackConfig(parseFallbackJson(content, userPath));
  }

  // Fallback to bundled config (relative to project root)
  const bundledPath = join(import.meta.dir, "../../config/fallback.json");
  if (existsSync(bundledPath)) {
    const content = await readFile(bundledPath, "utf-8");
    return validateFallbackConfig(parseFallbackJson(content, bundledPath));
  }

  // Default config if nothing found
  return validateFallbackConfig({
    providers: [
      {
        name: "anthropic",
        apiKeyEnv: "ANTHROPIC_API_KEY",
        healthEndpoint: "https://api.anthropic.com/v1/messages",
        priority: 1,
      },
      {
        name: "openai",
        apiKeyEnv: "OPENAI_API_KEY",
        healthEndpoint: "https://api.openai.com/v1/models",
        priority: 2,
      },
    ],
    maxRetries: 3,
    timeoutMs: 5000,
  });
}

// ─── Health Checks ───────────────────────────────────────────

/**
 * Check if a provider's API key is set in the environment.
 */
export function hasApiKey(provider: ProviderConfig): boolean {
  const key = process.env[provider.apiKeyEnv];
  return !!key && key.length > 0;
}

/**
 * Check if a provider is available (API key set + endpoint reachable).
 */
export async function checkProviderHealth(
  provider: ProviderConfig,
  timeoutMs: number = 5000
): Promise<ProviderHealthResult> {
  // First check: API key must be set
  if (!hasApiKey(provider)) {
    return {
      provider,
      healthy: false,
      reason: `API key not set (${provider.apiKeyEnv})`,
    };
  }

  // Second check: endpoint reachable (HEAD request with timeout)
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const endpoint = new URL(provider.healthEndpoint);
    const headers: Record<string, string> = {};
    if (!isLocalEndpoint(endpoint)) {
      if (provider.name === "anthropic") {
        headers["x-api-key"] = process.env[provider.apiKeyEnv] || "";
        headers["anthropic-version"] = "2023-06-01";
      } else {
        headers.Authorization = `Bearer ${process.env[provider.apiKeyEnv]}`;
      }
    }

    const response = await fetch(provider.healthEndpoint, {
      method: "HEAD",
      signal: controller.signal,
      headers,
    });

    clearTimeout(timeout);

    if (response.status === 401 || response.status === 403) {
      return {
        provider,
        healthy: false,
        reason: `Authentication failed (${response.status})`,
      };
    }
    if (response.status === 429) {
      return {
        provider,
        healthy: false,
        reason: "Rate limited (429)",
      };
    }

    const reachable = response.status < 500;

    return {
      provider,
      healthy: reachable,
      reason: reachable ? undefined : `Endpoint returned ${response.status}`,
    };
  } catch (err) {
    clearTimeout(timeout);
    const message = err instanceof Error ? err.message : "Unknown error";
    return {
      provider,
      healthy: false,
      reason: `Endpoint unreachable: ${message}`,
    };
  }
}

/**
 * Get ordered list of available providers (skip unavailable ones).
 * Sorted by priority (lower number = higher priority).
 */
export async function getAvailableProviders(config: FallbackConfig): Promise<ProviderConfig[]> {
  const sorted = [...config.providers].sort((a, b) => a.priority - b.priority);
  const results = await Promise.all(
    sorted.map((provider) => checkProviderHealth(provider, config.timeoutMs))
  );

  return results.filter((r) => r.healthy).map((r) => r.provider);
}

/**
 * Get the best available provider (first healthy one by priority).
 * Returns null if no providers are available.
 */
export async function getBestProvider(config: FallbackConfig): Promise<ProviderConfig | null> {
  const available = await getAvailableProviders(config);
  return available.length > 0 ? available[0] : null;
}

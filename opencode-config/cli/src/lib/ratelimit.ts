import { join } from "path";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";

// ─── Types ───────────────────────────────────────────────────

export interface RateLimitState {
  provider: string;
  requestsThisMinute: number;
  lastRequestTime: number;
  backoffUntil: number | null;
  consecutiveErrors: number;
}

interface RateLimitStore {
  [provider: string]: RateLimitState;
}

// ─── Constants ───────────────────────────────────────────────

const STATE_FILE = "ratelimit-state.json";
const ONE_MINUTE_MS = 60_000;
const BASE_BACKOFF_MS = 1_000; // 1 second base
const MAX_BACKOFF_MS = 300_000; // 5 minutes max

// ─── Rate Limiter Class ──────────────────────────────────────

export class RateLimiter {
  private configDir: string;
  private statePath: string;
  private store: RateLimitStore;

  constructor(configDir: string) {
    this.configDir = configDir;
    this.statePath = join(configDir, STATE_FILE);
    this.store = this.loadState();
  }

  /**
   * Load persisted rate limit state from disk.
   */
  private loadState(): RateLimitStore {
    if (!existsSync(this.statePath)) {
      return {};
    }

    try {
      const content = readFileSync(this.statePath, "utf-8");
      return JSON.parse(content) as RateLimitStore;
    } catch {
      return {};
    }
  }

  /**
   * Persist current state to disk.
   */
  private saveState(): void {
    try {
      if (!existsSync(this.configDir)) {
        mkdirSync(this.configDir, { recursive: true });
      }
      writeFileSync(this.statePath, JSON.stringify(this.store, null, 2), "utf-8");
    } catch {
      // State persistence should never crash the CLI
    }
  }

  /**
   * Get or initialize state for a provider.
   */
  private getProviderState(provider: string): RateLimitState {
    if (!this.store[provider]) {
      this.store[provider] = {
        provider,
        requestsThisMinute: 0,
        lastRequestTime: 0,
        backoffUntil: null,
        consecutiveErrors: 0,
      };
    }

    // Reset minute counter if more than a minute has passed
    const now = Date.now();
    const state = this.store[provider];
    if (now - state.lastRequestTime > ONE_MINUTE_MS) {
      state.requestsThisMinute = 0;
    }

    return state;
  }

  /**
   * Check if a request can be made to the given provider.
   * Returns false if currently in backoff period.
   */
  async canMakeRequest(provider: string): Promise<boolean> {
    const state = this.getProviderState(provider);
    const now = Date.now();

    // Check if we're in a backoff period
    if (state.backoffUntil && now < state.backoffUntil) {
      return false;
    }

    // Clear backoff if it has expired
    if (state.backoffUntil && now >= state.backoffUntil) {
      state.backoffUntil = null;
    }

    return true;
  }

  /**
   * Record a successful request to a provider.
   */
  recordRequest(provider: string): void {
    const state = this.getProviderState(provider);
    const now = Date.now();

    state.requestsThisMinute++;
    state.lastRequestTime = now;
    state.consecutiveErrors = 0; // Reset on success
    state.backoffUntil = null;

    this.saveState();
  }

  /**
   * Record an error response from a provider.
   * Implements exponential backoff on 429 (rate limit) responses.
   */
  recordError(provider: string, statusCode: number): void {
    const state = this.getProviderState(provider);
    state.consecutiveErrors++;
    state.lastRequestTime = Date.now();

    if (statusCode === 429) {
      // Exponential backoff: 1s, 2s, 4s, 8s, 16s, ... up to MAX_BACKOFF_MS
      const backoffMs = Math.min(
        BASE_BACKOFF_MS * Math.pow(2, state.consecutiveErrors - 1),
        MAX_BACKOFF_MS
      );
      state.backoffUntil = Date.now() + backoffMs;
    } else if (statusCode >= 500) {
      // Server errors: shorter backoff
      const backoffMs = Math.min(
        BASE_BACKOFF_MS * state.consecutiveErrors,
        MAX_BACKOFF_MS
      );
      state.backoffUntil = Date.now() + backoffMs;
    }

    this.saveState();
  }

  /**
   * Get the remaining backoff time in milliseconds for a provider.
   * Returns 0 if not in backoff.
   */
  getBackoffTime(provider: string): number {
    const state = this.getProviderState(provider);
    const now = Date.now();

    if (!state.backoffUntil || now >= state.backoffUntil) {
      return 0;
    }

    return state.backoffUntil - now;
  }

  /**
   * Reset all rate limit state for a provider.
   */
  reset(provider: string): void {
    delete this.store[provider];
    this.saveState();
  }

  /**
   * Get current state for a provider (for display/debugging).
   */
  getState(provider: string): RateLimitState {
    return this.getProviderState(provider);
  }

  /**
   * Get all tracked providers.
   */
  getAllProviders(): string[] {
    return Object.keys(this.store);
  }
}

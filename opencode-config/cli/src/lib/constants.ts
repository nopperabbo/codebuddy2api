// ─── Version ─────────────────────────────────────────────────
export const VERSION = "1.9.1";

// ─── GitHub ──────────────────────────────────────────────────
export const GITHUB_REPO = "JCETools-Petra/JCE-Opencode-Tools";
export const GITHUB_RAW_BASE = `https://raw.githubusercontent.com/${GITHUB_REPO}/main`;

// ─── Model Pricing (per 1K tokens) ──────────────────────────
export const COST_PER_1K: Record<string, { input: number; output: number }> = {
  "claude-sonnet": { input: 0.003, output: 0.015 },
  "claude-opus": { input: 0.015, output: 0.075 },
  "claude-haiku": { input: 0.00025, output: 0.00125 },
  "gpt-4o": { input: 0.005, output: 0.015 },
  "gpt-4o-mini": { input: 0.00015, output: 0.0006 },
  "deepseek": { input: 0.00014, output: 0.00028 },
  "gemini-pro": { input: 0.00125, output: 0.005 },
  "gemini-flash": { input: 0.000075, output: 0.0003 },
};

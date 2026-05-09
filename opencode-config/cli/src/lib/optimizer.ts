import type { Profile } from "../types.js";
import type { TokenUsageEntry } from "./tokens.js";
import { COST_PER_1K } from "./constants.js";

// ─── Types ───────────────────────────────────────────────────

export interface OptimizationSuggestion {
  currentProfile: string;
  suggestedProfile: string;
  estimatedSavings: string;
  reason: string;
}

// ─── Analysis Helpers ────────────────────────────────────────

/**
 * Get the average tokens per request for a set of entries.
 */
function getAverageTokens(entries: TokenUsageEntry[]): { input: number; output: number } {
  if (entries.length === 0) return { input: 0, output: 0 };

  const totals = entries.reduce(
    (acc, e) => ({
      input: acc.input + e.inputTokens,
      output: acc.output + e.outputTokens,
    }),
    { input: 0, output: 0 }
  );

  return {
    input: Math.round(totals.input / entries.length),
    output: Math.round(totals.output / entries.length),
  };
}

/**
 * Estimate cost for a model given token counts.
 */
function estimateCost(model: string, inputTokens: number, outputTokens: number): number {
  const lowerModel = model.toLowerCase();
  let rates: { input: number; output: number } | undefined;
  for (const [key, value] of Object.entries(COST_PER_1K)) {
    if (lowerModel.includes(key)) {
      rates = value;
      break;
    }
  }
  if (!rates) return 0;
  return (inputTokens / 1000) * rates.input + (outputTokens / 1000) * rates.output;
}

/**
 * Get the tier of a model (expensive, moderate, cheap).
 */
function getModelTier(model: string): "expensive" | "moderate" | "cheap" {
  if (model.includes("opus") || model.includes("gpt-4-turbo")) return "expensive";
  if (model.includes("sonnet") || (model.includes("gpt-4o") && !model.includes("mini"))) return "moderate";
  return "cheap";
}

// ─── Public API ──────────────────────────────────────────────

/**
 * Analyze token usage data and suggest cost optimizations.
 */
export function analyzeCostOptimizations(
  usage: TokenUsageEntry[],
  profiles: Profile[]
): OptimizationSuggestion[] {
  const suggestions: OptimizationSuggestion[] = [];

  if (usage.length === 0) return suggestions;

  // Group usage by model
  const byModel: Record<string, TokenUsageEntry[]> = {};
  for (const entry of usage) {
    if (!byModel[entry.model]) byModel[entry.model] = [];
    byModel[entry.model].push(entry);
  }

  for (const [model, entries] of Object.entries(byModel)) {
    const tier = getModelTier(model);
    const avgTokens = getAverageTokens(entries);

    // Suggestion 1: Expensive model used for small requests
    if (tier === "expensive" && avgTokens.input < 500 && avgTokens.output < 500) {
      const currentCost = estimateCost(model, avgTokens.input * entries.length, avgTokens.output * entries.length);
      const cheaperModel = "gpt-4o-mini";
      const cheaperCost = estimateCost(cheaperModel, avgTokens.input * entries.length, avgTokens.output * entries.length);
      const savings = currentCost > 0 ? Math.round((1 - cheaperCost / currentCost) * 100) : 0;

      // Find the profile using this model
      const currentProfile = profiles.find((p) => p.model === model);
      const suggestedProfile = profiles.find((p) => p.model === cheaperModel) || profiles.find((p) => p.provider === "auto") || profiles[0];

      if (currentProfile && suggestedProfile) {
        suggestions.push({
          currentProfile: currentProfile.id,
          suggestedProfile: suggestedProfile.id,
          estimatedSavings: `~${savings}% cheaper`,
          reason: `Using expensive model (${model}) for small requests (avg ${avgTokens.input} input tokens). A faster, cheaper model would suffice.`,
        });
      }
    }

    // Suggestion 2: Moderate model used for very simple requests
    if (tier === "moderate" && avgTokens.input < 200 && avgTokens.output < 200) {
      const currentProfile = profiles.find((p) => p.model === model);
      const suggestedProfile = profiles.find((p) => p.provider === "auto") || profiles[0];

      if (currentProfile && suggestedProfile && currentProfile.id !== suggestedProfile.id) {
        suggestions.push({
          currentProfile: currentProfile.id,
          suggestedProfile: suggestedProfile.id,
          estimatedSavings: "~60% cheaper",
          reason: `Using ${model} for very short requests. Consider the budget profile for simple tasks.`,
        });
      }
    }

    // Suggestion 3: High volume on expensive model — suggest batching or downgrade
    if (tier === "expensive" && entries.length > 20) {
      const currentProfile = profiles.find((p) => p.model === model);
      const suggestedProfile = profiles.find((p) => p.provider === "anthropic" && p.model?.includes("sonnet"));

      if (currentProfile && suggestedProfile && currentProfile.id !== suggestedProfile.id) {
        suggestions.push({
          currentProfile: currentProfile.id,
          suggestedProfile: suggestedProfile.id,
          estimatedSavings: "~40% cheaper",
          reason: `High request volume (${entries.length} requests) on expensive model. Consider using Sonnet for routine tasks and reserving Opus for complex ones.`,
        });
      }
    }

    // Suggestion 4: Using smart routing could help
    if (Object.keys(byModel).length === 1 && entries.length > 10) {
      const currentProfile = profiles.find((p) => p.model === model);
      if (currentProfile && tier !== "cheap") {
        suggestions.push({
          currentProfile: currentProfile.id,
          suggestedProfile: "auto (smart routing)",
          estimatedSavings: "~20-50% cheaper",
          reason: `All ${entries.length} requests use the same model. Enable smart routing ('opencode-jce route') to automatically select cheaper models for simple tasks.`,
        });
      }
    }
  }

  return suggestions;
}

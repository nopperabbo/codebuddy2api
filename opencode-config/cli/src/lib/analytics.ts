import { TokenUsageEntry } from "./tokens.js";

// ─── Types ───────────────────────────────────────────────────

export interface AnalyticsSummary {
  totalRequests: number;
  totalTokens: { input: number; output: number };
  totalCost: number;
  topAgents: Array<{ agent: string; requests: number; cost: number }>;
  topModels: Array<{ model: string; requests: number; cost: number }>;
  dailyUsage: Array<{ date: string; requests: number; cost: number }>;
  averageComplexity: string;
  costTrend: "increasing" | "decreasing" | "stable";
}

// ─── Analytics Generator ─────────────────────────────────────

/**
 * Generate analytics summary from token usage data.
 */
export function generateAnalytics(
  tokenData: TokenUsageEntry[],
  period: "week" | "month" | "all"
): AnalyticsSummary {
  // Filter data by period
  const filteredData = filterByPeriod(tokenData, period);

  // Calculate totals
  const totalRequests = filteredData.length;
  const totalTokens = filteredData.reduce(
    (acc, e) => ({
      input: acc.input + e.inputTokens,
      output: acc.output + e.outputTokens,
    }),
    { input: 0, output: 0 }
  );
  const totalCost = filteredData.reduce((sum, e) => sum + e.cost, 0);

  // Top agents
  const topAgents = getTopAgents(filteredData);

  // Top models
  const topModels = getTopModels(filteredData);

  // Daily usage
  const dailyUsage = getDailyUsage(filteredData);

  // Average complexity based on token count per request
  const averageComplexity = calculateComplexity(filteredData);

  // Cost trend
  const costTrend = calculateCostTrend(filteredData);

  return {
    totalRequests,
    totalTokens,
    totalCost,
    topAgents,
    topModels,
    dailyUsage,
    averageComplexity,
    costTrend,
  };
}

// ─── Internal Helpers ────────────────────────────────────────

function filterByPeriod(data: TokenUsageEntry[], period: "week" | "month" | "all"): TokenUsageEntry[] {
  if (period === "all") return data;

  const now = new Date();
  let cutoff: Date;

  if (period === "week") {
    cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  } else {
    // month
    cutoff = new Date(now.getFullYear(), now.getMonth(), 1);
  }

  return data.filter((e) => new Date(e.timestamp) >= cutoff);
}

function getTopAgents(data: TokenUsageEntry[]): Array<{ agent: string; requests: number; cost: number }> {
  const agentMap = new Map<string, { requests: number; cost: number }>();

  for (const entry of data) {
    const existing = agentMap.get(entry.agent) || { requests: 0, cost: 0 };
    existing.requests++;
    existing.cost += entry.cost;
    agentMap.set(entry.agent, existing);
  }

  return Array.from(agentMap.entries())
    .map(([agent, stats]) => ({ agent, ...stats }))
    .sort((a, b) => b.requests - a.requests)
    .slice(0, 5);
}

function getTopModels(data: TokenUsageEntry[]): Array<{ model: string; requests: number; cost: number }> {
  const modelMap = new Map<string, { requests: number; cost: number }>();

  for (const entry of data) {
    const existing = modelMap.get(entry.model) || { requests: 0, cost: 0 };
    existing.requests++;
    existing.cost += entry.cost;
    modelMap.set(entry.model, existing);
  }

  return Array.from(modelMap.entries())
    .map(([model, stats]) => ({ model, ...stats }))
    .sort((a, b) => b.requests - a.requests)
    .slice(0, 5);
}

function getDailyUsage(data: TokenUsageEntry[]): Array<{ date: string; requests: number; cost: number }> {
  const dayMap = new Map<string, { requests: number; cost: number }>();

  for (const entry of data) {
    const date = entry.timestamp.split("T")[0]; // YYYY-MM-DD
    const existing = dayMap.get(date) || { requests: 0, cost: 0 };
    existing.requests++;
    existing.cost += entry.cost;
    dayMap.set(date, existing);
  }

  return Array.from(dayMap.entries())
    .map(([date, stats]) => ({ date, ...stats }))
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-7); // Last 7 days with data
}

function calculateComplexity(data: TokenUsageEntry[]): string {
  if (data.length === 0) return "N/A";

  const avgTokens =
    data.reduce((sum, e) => sum + e.inputTokens + e.outputTokens, 0) / data.length;

  if (avgTokens < 500) return "Low";
  if (avgTokens < 2000) return "Medium";
  if (avgTokens < 5000) return "High";
  return "Very High";
}

function calculateCostTrend(data: TokenUsageEntry[]): "increasing" | "decreasing" | "stable" {
  if (data.length < 4) return "stable";

  // Split data into two halves and compare average daily cost
  const sorted = [...data].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  const midpoint = Math.floor(sorted.length / 2);
  const firstHalf = sorted.slice(0, midpoint);
  const secondHalf = sorted.slice(midpoint);

  const firstAvgCost = firstHalf.reduce((sum, e) => sum + e.cost, 0) / firstHalf.length;
  const secondAvgCost = secondHalf.reduce((sum, e) => sum + e.cost, 0) / secondHalf.length;

  const changePercent = ((secondAvgCost - firstAvgCost) / (firstAvgCost || 1)) * 100;

  if (changePercent > 15) return "increasing";
  if (changePercent < -15) return "decreasing";
  return "stable";
}

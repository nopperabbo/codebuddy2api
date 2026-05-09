import { join, dirname } from "path";
import { existsSync, mkdirSync } from "fs";
import { readFile, writeFile } from "fs/promises";
import { getConfigDir } from "./config.js";
import type { Agent, AgentsConfig } from "../types.js";

/**
 * Get the path to the agents.json config file.
 */
export function getAgentsPath(): string {
  return join(getConfigDir(), "agents.json");
}

/**
 * Load all agents from agents.json.
 * Returns empty array if file doesn't exist.
 */
export async function loadAgents(): Promise<Agent[]> {
  const agentsPath = getAgentsPath();

  if (!existsSync(agentsPath)) {
    return [];
  }

  const content = await readFile(agentsPath, "utf-8");
  let config: AgentsConfig;
  try {
    config = JSON.parse(content);
  } catch {
    throw new Error(`Failed to parse ${agentsPath}: invalid JSON`);
  }
  return config.agents || [];
}

/**
 * Save agents array to agents.json.
 */
export async function saveAgents(agents: Agent[]): Promise<void> {
  const agentsPath = getAgentsPath();
  const dir = dirname(agentsPath);

  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  const config: AgentsConfig = { agents };
  await writeFile(agentsPath, JSON.stringify(config, null, 2), "utf-8");
}

/**
 * Find an agent by ID.
 */
export async function findAgent(id: string): Promise<Agent | undefined> {
  const agents = await loadAgents();
  return agents.find((a) => a.id === id);
}

/**
 * Add a new agent. Returns false if ID already exists.
 */
export async function addAgent(agent: Agent): Promise<boolean> {
  const agents = await loadAgents();

  if (agents.some((a) => a.id === agent.id)) {
    return false;
  }

  agents.push(agent);
  await saveAgents(agents);
  return true;
}

/**
 * Remove an agent by ID. Returns false if not found.
 */
export async function removeAgent(id: string): Promise<boolean> {
  const agents = await loadAgents();
  const index = agents.findIndex((a) => a.id === id);

  if (index === -1) {
    return false;
  }

  agents.splice(index, 1);
  await saveAgents(agents);
  return true;
}

/**
 * Update an agent by ID. Returns false if not found.
 */
export async function updateAgent(id: string, updates: Partial<Omit<Agent, "id">>): Promise<boolean> {
  const agents = await loadAgents();
  const index = agents.findIndex((a) => a.id === id);

  if (index === -1) {
    return false;
  }

  agents[index] = { ...agents[index], ...updates };
  await saveAgents(agents);
  return true;
}

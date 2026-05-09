import { join, basename, resolve, relative, isAbsolute } from "path";
import { existsSync, readdirSync } from "fs";
import { readFile } from "fs/promises";
import { getConfigDir } from "./config.js";
import { loadAgents, saveAgents } from "./agents.js";

/**
 * Get the path to the prompts directory.
 */
export function getPromptsDir(): string {
  return join(getConfigDir(), "prompts");
}

/**
 * List all available prompt template names (without .txt extension).
 */
export function listPromptTemplates(): string[] {
  const promptsDir = getPromptsDir();

  if (!existsSync(promptsDir)) {
    return [];
  }

  return readdirSync(promptsDir)
    .filter((f) => f.endsWith(".txt"))
    .map((f) => basename(f, ".txt"));
}

/**
 * Load the content of a prompt template by name.
 * Returns null if not found.
 */
export async function loadPromptTemplate(name: string): Promise<string | null> {
  const promptsDir = getPromptsDir();
  if (!/^[\w-]+$/.test(name)) {
    throw new Error(`Invalid template name: only letters, numbers, underscores, and hyphens are allowed`);
  }

  const promptPath = join(promptsDir, `${name}.txt`);

  const resolvedPath = resolve(promptPath);
  const resolvedDir = resolve(promptsDir);
  const rel = relative(resolvedDir, resolvedPath);
  if (rel.startsWith("..") || isAbsolute(rel)) {
    throw new Error(`Invalid template name: path traversal detected`);
  }

  if (!existsSync(promptPath)) {
    return null;
  }

  return await readFile(promptPath, "utf-8");
}

/**
 * Apply a prompt template to an agent by prepending it to the system prompt.
 * Returns false if agent or template not found.
 */
export async function applyPromptToAgent(templateName: string, agentId: string): Promise<{ success: boolean; error?: string }> {
  const template = await loadPromptTemplate(templateName);

  if (template === null) {
    return { success: false, error: `Template "${templateName}" not found.` };
  }

  const agents = await loadAgents();
  const agent = agents.find((a) => a.id === agentId);

  if (!agent) {
    return { success: false, error: `Agent "${agentId}" not found.` };
  }

  // Prepend template to system prompt (avoid duplicating if already applied)
  const startMarker = `[template:${templateName}]\n`;
  const endMarker = `\n[/template]\n\n`;

  if (agent.systemPrompt.includes("[template:")) {
    // Replace existing template(s)
    agent.systemPrompt = agent.systemPrompt.replace(
      /\[template:[\w-]+\][\s\S]*?\[\/template\]\n\n/g,
      `${startMarker}${template}${endMarker}`
    );
  } else {
    agent.systemPrompt = `${startMarker}${template}${endMarker}${agent.systemPrompt}`;
  }

  await saveAgents(agents);
  return { success: true };
}

/**
 * Reset an agent's system prompt by removing any prepended template.
 * Returns false if agent not found.
 */
export async function resetAgentPrompt(agentId: string): Promise<{ success: boolean; error?: string }> {
  const agents = await loadAgents();
  const agent = agents.find((a) => a.id === agentId);

  if (!agent) {
    return { success: false, error: `Agent "${agentId}" not found.` };
  }

  // Remove all template marker prefixes if present
  const cleaned = agent.systemPrompt.replace(/\[template:[\w-]+\][\s\S]*?\[\/template\]\n\n/g, '');
  if (cleaned !== agent.systemPrompt) {
    agent.systemPrompt = cleaned;
    await saveAgents(agents);
  }

  return { success: true };
}

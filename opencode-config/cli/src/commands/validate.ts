import { Command } from "commander";
import { readdirSync, existsSync } from "fs";
import { join } from "path";
import { getConfigDir, loadConfigFile } from "../lib/config.js";
import { validateAgainstSchema } from "../lib/schema.js";
import { success, error, heading, info } from "../lib/ui.js";
import { EXIT_SUCCESS, EXIT_ERROR } from "../types.js";

interface ConfigFileEntry {
  relativePath: string;
  schemaFile: string;
  label: string;
}

function getConfigFilesToValidate(): ConfigFileEntry[] {
  const entries: ConfigFileEntry[] = [
    { relativePath: "agents.json", schemaFile: "agents.schema.json", label: "agents.json" },
    { relativePath: "mcp.json", schemaFile: "mcp.schema.json", label: "mcp.json" },
    { relativePath: "lsp.json", schemaFile: "lsp.schema.json", label: "lsp.json" },
    { relativePath: "fallback.json", schemaFile: "fallback.schema.json", label: "fallback.json" },
  ];

  // Add all profile files
  const profilesDir = join(getConfigDir(), "profiles");
  if (existsSync(profilesDir)) {
    const profileFiles = readdirSync(profilesDir).filter((f) => f.endsWith(".json"));
    for (const file of profileFiles) {
      entries.push({
        relativePath: join("profiles", file),
        schemaFile: "profile.schema.json",
        label: `profiles/${file}`,
      });
    }
  }

  return entries;
}

export const validateCommand = new Command("validate")
  .description("Validate all configuration files against JSON schemas")
  .action(async () => {
    heading("Config Validation");

    const configDir = getConfigDir();
    if (!existsSync(configDir)) {
      error(`Config directory not found: ${configDir}`);
      info("Run the installer first to deploy configuration files.");
      process.exit(EXIT_ERROR);
    }

    const entries = getConfigFilesToValidate();
    let hasErrors = false;

    for (const entry of entries) {
      try {
        const data = await loadConfigFile(entry.relativePath);
        const result = await validateAgainstSchema(data, entry.schemaFile);

        if (result.valid) {
          success(`${entry.label} — valid`);
        } else {
          hasErrors = true;
          error(`${entry.label} — invalid`);
          for (const err of result.errors) {
            console.log(`      ${err}`);
          }
        }
      } catch (err) {
        hasErrors = true;
        const msg = err instanceof Error ? err.message : String(err);
        error(`${entry.label} — ${msg}`);
      }
    }

    console.log();
    if (hasErrors) {
      process.exit(EXIT_ERROR);
    } else {
      info(`All ${entries.length} config files are valid.`);
      process.exit(EXIT_SUCCESS);
    }
  });

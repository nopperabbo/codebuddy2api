import Ajv from "ajv";
import { readFile } from "fs/promises";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const ajv = new Ajv({ allErrors: true, strict: false });

/** Cache for compiled validators */
const validatorCache = new Map<string, ReturnType<typeof ajv.compile>>();

/**
 * Get the path to the schemas directory (relative to the repo root).
 * Since this CLI runs via `bun run src/index.ts` or as a global install,
 * we resolve relative to the package root.
 */
function getSchemasDir(): string {
  // When running from source: resolve from this file's location
  const thisFile = fileURLToPath(import.meta.url);
  const srcDir = dirname(dirname(thisFile)); // src/lib -> src -> root
  return join(srcDir, "..", "schemas");
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * Load a JSON schema file from the schemas/ directory.
 */
async function loadSchema(schemaFileName: string): Promise<object> {
  const schemaPath = join(getSchemasDir(), schemaFileName);
  const content = await readFile(schemaPath, "utf-8");
  try {
    return JSON.parse(content);
  } catch {
    throw new Error(`Failed to parse ${schemaPath}: invalid JSON`);
  }
}

/**
 * Get or create a compiled validator for a schema file.
 * Validators are cached for performance on repeated validations.
 */
async function getValidator(schemaFileName: string) {
  if (validatorCache.has(schemaFileName)) {
    return validatorCache.get(schemaFileName)!;
  }

  const schema = await loadSchema(schemaFileName);
  const validate = ajv.compile(schema);
  validatorCache.set(schemaFileName, validate);
  return validate;
}

/**
 * Validate a data object against a named schema file.
 */
export async function validateAgainstSchema(
  data: unknown,
  schemaFileName: string
): Promise<ValidationResult> {
  const validate = await getValidator(schemaFileName);
  const valid = validate(data);

  if (valid) {
    return { valid: true, errors: [] };
  }

  const errors = (validate.errors || []).map((err) => {
    const path = err.instancePath || "/";
    return `${path} ${err.message}`;
  });

  return { valid: false, errors };
}

/**
 * Cross-Model Verify Plugin
 * 
 * Sanitizes cross-model metadata when switching between AI providers
 * (e.g., Claude ↔ Gemini). Prevents validation errors caused by
 * provider-specific thinking signatures and metadata leaking across models.
 * 
 * What it does:
 * - Strips Gemini thinking metadata (thoughtSignature, thinkingMetadata, google.*)
 *   before sending context to Claude
 * - Strips Claude thinking fields (signature on thinking/redacted_thinking blocks)
 *   before sending context to Gemini
 * - Operates as a hook on message/request events — fully transparent
 */

// ─── Model Detection ─────────────────────────────────────────────

const CLAUDE_PATTERNS = [/claude/i, /anthropic/i, /opus/i, /sonnet/i, /haiku/i];
const GEMINI_PATTERNS = [/gemini/i, /google/i, /palm/i];
const GEMINI_SIGNATURE_FIELDS = ['thoughtSignature', 'thinkingBudgetMillis', 'thoughtsGenerationEnabled'];
const CLAUDE_SIGNATURE_FIELDS = ['signature'];

function getModelFamily(model) {
  if (!model || typeof model !== 'string') return 'unknown';
  if (CLAUDE_PATTERNS.some(p => p.test(model))) return 'claude';
  if (GEMINI_PATTERNS.some(p => p.test(model))) return 'gemini';
  return 'unknown';
}

function isPlainObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

// ─── Sanitization Functions ──────────────────────────────────────

function stripGeminiThinkingMetadata(part, preserveNonSignature = true) {
  let stripped = 0;

  if ('thoughtSignature' in part) {
    delete part.thoughtSignature;
    stripped++;
  }
  if ('thinkingMetadata' in part) {
    delete part.thinkingMetadata;
    stripped++;
  }

  if (isPlainObject(part.metadata)) {
    const metadata = part.metadata;
    if (isPlainObject(metadata.google)) {
      const google = metadata.google;
      for (const field of GEMINI_SIGNATURE_FIELDS) {
        if (field in google) {
          delete google[field];
          stripped++;
        }
      }
      if (!preserveNonSignature || Object.keys(google).length === 0) {
        delete metadata.google;
      }
      if (Object.keys(metadata).length === 0) {
        delete part.metadata;
      }
    }
  }

  return { part, stripped };
}

function stripClaudeThinkingFields(part) {
  let stripped = 0;

  if (part.type === 'thinking' || part.type === 'redacted_thinking') {
    for (const field of CLAUDE_SIGNATURE_FIELDS) {
      if (field in part) {
        delete part[field];
        stripped++;
      }
    }
  }

  // Also strip standalone signature fields that look like crypto signatures
  if ('signature' in part && typeof part.signature === 'string') {
    if (part.signature.length >= 50) {
      delete part.signature;
      stripped++;
    }
  }

  return { part, stripped };
}

function sanitizePart(part, targetFamily, preserveNonSignature) {
  if (!isPlainObject(part)) return { part, stripped: 0 };

  let totalStripped = 0;
  const partObj = { ...part };

  if (targetFamily === 'claude') {
    const result = stripGeminiThinkingMetadata(partObj, preserveNonSignature);
    totalStripped += result.stripped;
  } else if (targetFamily === 'gemini') {
    const result = stripClaudeThinkingFields(partObj);
    totalStripped += result.stripped;
  }

  return { part: partObj, stripped: totalStripped };
}

function sanitizePartsArray(parts, targetFamily, preserveNonSignature) {
  let totalStripped = 0;
  const sanitizedParts = parts.map(part => {
    const result = sanitizePart(part, targetFamily, preserveNonSignature);
    totalStripped += result.stripped;
    return result.part;
  });
  return { parts: sanitizedParts, stripped: totalStripped };
}

function sanitizeMessages(messages, targetFamily, preserveNonSignature) {
  let totalStripped = 0;
  const sanitizedMessages = messages.map(message => {
    if (!isPlainObject(message)) return message;
    const messageObj = { ...message };

    if (Array.isArray(messageObj.content)) {
      const result = sanitizePartsArray(messageObj.content, targetFamily, preserveNonSignature);
      messageObj.content = result.parts;
      totalStripped += result.stripped;
    }

    // Also handle Gemini-style 'parts' field
    if (Array.isArray(messageObj.parts)) {
      const result = sanitizePartsArray(messageObj.parts, targetFamily, preserveNonSignature);
      messageObj.parts = result.parts;
      totalStripped += result.stripped;
    }

    return messageObj;
  });
  return { messages: sanitizedMessages, stripped: totalStripped };
}

function deepSanitize(obj, targetFamily, preserveNonSignature = true) {
  if (!isPlainObject(obj)) return { obj, stripped: 0 };

  let totalStripped = 0;
  const result = { ...obj };

  // Gemini format: contents[].parts[]
  if (Array.isArray(result.contents)) {
    for (const content of result.contents) {
      if (isPlainObject(content) && Array.isArray(content.parts)) {
        const sanitized = sanitizePartsArray(content.parts, targetFamily, preserveNonSignature);
        content.parts = sanitized.parts;
        totalStripped += sanitized.stripped;
      }
    }
  }

  // OpenAI/Claude format: messages[].content[]
  if (Array.isArray(result.messages)) {
    const sanitized = sanitizeMessages(result.messages, targetFamily, preserveNonSignature);
    result.messages = sanitized.messages;
    totalStripped += sanitized.stripped;
  }

  // Extra body (some proxies wrap messages here)
  if (isPlainObject(result.extra_body) && Array.isArray(result.extra_body.messages)) {
    const sanitized = sanitizeMessages(result.extra_body.messages, targetFamily, preserveNonSignature);
    result.extra_body = { ...result.extra_body, messages: sanitized.messages };
    totalStripped += sanitized.stripped;
  }

  return { obj: result, stripped: totalStripped };
}

// ─── Stats Tracking ──────────────────────────────────────────────

let stats = {
  totalSanitized: 0,
  totalStripped: 0,
  byFamily: { claude: 0, gemini: 0 },
  lastSanitized: null
};

// ─── Plugin Export ───────────────────────────────────────────────

export default async (input, options) => {
  let lastModel = null;

  return {
    // Hook into message events to sanitize cross-model metadata
    hooks: {
      // Before a message is sent to the model
      message: {
        send: {
          before: (data) => {
            try {
              const currentModel = data?.model || data?.options?.model || '';
              const targetFamily = getModelFamily(currentModel);

              if (targetFamily === 'unknown') return data;

              // Track model switches
              if (lastModel && getModelFamily(lastModel) !== targetFamily) {
                // Model switch detected — sanitize
                const result = deepSanitize(data, targetFamily);
                if (result.stripped > 0) {
                  stats.totalSanitized++;
                  stats.totalStripped += result.stripped;
                  stats.byFamily[targetFamily] = (stats.byFamily[targetFamily] || 0) + result.stripped;
                  stats.lastSanitized = new Date().toISOString();
                }
                lastModel = currentModel;
                return result.obj;
              }

              lastModel = currentModel;
              return data;
            } catch (err) {
              // Never crash — just pass through
              return data;
            }
          }
        }
      },

      // After tool execution — track model usage
      tool: {
        execute: {
          after: (data) => {
            try {
              if (data?.model) {
                lastModel = data.model;
              }
            } catch {}
          }
        }
      }
    },

    // Event handler for session-level tracking
    event: async (event, data) => {
      try {
        if (event === 'session.created') {
          // Reset tracking for new session
          lastModel = null;
        }
      } catch {}
    }
  };
};

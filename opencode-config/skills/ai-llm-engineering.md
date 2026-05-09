# Skill: AI/LLM Engineering
# Loaded on-demand when task involves RAG, embeddings, vector databases, prompt engineering, LLM evaluation, or fine-tuning

## Auto-Detect

Trigger this skill when:
- Task mentions: RAG, embeddings, vector database, LLM, prompt engineering, fine-tuning, AI
- Files: `prompts/`, `embeddings/`, `*.prompt`, `rag/`, `chains/`
- Patterns: retrieval augmented generation, semantic search, chat completion
- `package.json` contains: `openai`, `@anthropic-ai/sdk`, `langchain`, `@pinecone-database/pinecone`

---

## Decision Tree: LLM Architecture

```
What are you building?
+-- Question answering over your data?
|   +-- RAG pipeline (retrieve then augment then generate)
+-- Structured data extraction?
|   +-- Function calling / tool use with schema validation
+-- Multi-step reasoning?
|   +-- Predictable steps? -> Chain/pipeline (deterministic flow)
|   +-- Dynamic steps? -> Agent with tool access (LLM decides flow)
+-- Classification/labeling?
|   +-- < 20 categories? -> Few-shot prompting (no fine-tune needed)
|   +-- Domain-specific, high accuracy? -> Fine-tuned model
+-- Code generation?
|   +-- RAG with codebase context + specialized model
+-- Conversational?
    +-- Chat with memory (sliding window + summary)
```

## Decision Tree: Vector Database

```
+-- < 100K documents, simple use case? -> SQLite + pgvector
+-- Need managed, scalable? -> Pinecone / Weaviate Cloud
+-- Self-hosted, full control? -> Qdrant / Milvus
+-- Already using PostgreSQL? -> pgvector extension
+-- Need hybrid search (vector + keyword)? -> Weaviate / Elasticsearch
+-- Need multi-tenancy? -> Pinecone (namespaces) / Qdrant (collections)
```

---

## RAG Pipeline Implementation

```typescript
import { OpenAI } from 'openai';
import { QdrantClient } from '@qdrant/js-client-rest';

interface RAGConfig {
  chunkSize: number;        // 512-1024 tokens typically
  chunkOverlap: number;     // 10-20% of chunk size
  topK: number;             // 3-10 results
  scoreThreshold: number;   // Minimum similarity (0.7-0.8)
  rerankEnabled: boolean;
}

class RAGPipeline {
  constructor(
    private readonly llm: OpenAI,
    private readonly vectorDb: QdrantClient,
    private readonly config: RAGConfig
  ) {}

  // Step 1: Chunking with overlap
  chunkDocument(text: string): Chunk[] {
    const chunks: Chunk[] = [];
    const sentences = this.splitIntoSentences(text);
    let currentChunk: string[] = [];
    let currentTokens = 0;

    for (const sentence of sentences) {
      const sentenceTokens = this.countTokens(sentence);

      if (currentTokens + sentenceTokens > this.config.chunkSize && currentChunk.length > 0) {
        chunks.push({
          text: currentChunk.join(' '),
          tokenCount: currentTokens,
          metadata: { startSentence: chunks.length * this.config.chunkSize },
        });

        // Keep overlap
        const overlapTokens = Math.floor(this.config.chunkSize * 0.15);
        while (currentTokens > overlapTokens && currentChunk.length > 1) {
          currentTokens -= this.countTokens(currentChunk.shift()!);
        }
      }

      currentChunk.push(sentence);
      currentTokens += sentenceTokens;
    }

    if (currentChunk.length > 0) {
      chunks.push({ text: currentChunk.join(' '), tokenCount: currentTokens });
    }

    return chunks;
  }

  // Step 2: Embedding
  async embedChunks(chunks: Chunk[]): Promise<EmbeddedChunk[]> {
    const batchSize = 100;
    const results: EmbeddedChunk[] = [];

    for (let i = 0; i < chunks.length; i += batchSize) {
      const batch = chunks.slice(i, i + batchSize);
      const response = await this.llm.embeddings.create({
        model: 'text-embedding-3-small',
        input: batch.map(c => c.text),
        dimensions: 1024, // Matryoshka dimensionality reduction
      });

      for (let j = 0; j < batch.length; j++) {
        results.push({ ...batch[j], embedding: response.data[j].embedding });
      }
    }
    return results;
  }

  // Step 3: Retrieval
  async retrieve(query: string): Promise<RetrievedChunk[]> {
    const queryEmbedding = await this.embedQuery(query);

    const results = await this.vectorDb.search('documents', {
      vector: queryEmbedding,
      limit: this.config.topK * 2, // Over-fetch for reranking
      score_threshold: this.config.scoreThreshold,
      with_payload: true,
    });

    if (this.config.rerankEnabled) {
      return this.rerank(query, results);
    }
    return results.slice(0, this.config.topK);
  }

  // Step 4: Augmented generation
  async generate(query: string, context: RetrievedChunk[]): Promise<string> {
    const contextText = context
      .map((c, i) => `[Source ${i + 1}]: ${c.payload.text}`)
      .join('\n\n');

    const response = await this.llm.chat.completions.create({
      model: 'gpt-4o',
      messages: [
        {
          role: 'system',
          content: [
            'Answer questions based ONLY on the provided context.',
            'If context is insufficient, say so explicitly.',
            'Cite sources using [Source N] notation.',
          ].join('\n'),
        },
        { role: 'user', content: `Context:\n${contextText}\n\nQuestion: ${query}` },
      ],
      temperature: 0.1,
      max_tokens: 1000,
    });

    return response.choices[0].message.content!;
  }
}
```

---

## Prompt Engineering Patterns

```typescript
// Pattern 1: Chain of Thought (CoT)
const cotPrompt = [
  'Solve this step by step:',
  '1. First, identify the key information',
  '2. Then, determine what approach to use',
  '3. Work through the solution',
  '4. Verify your answer',
  '',
  'Problem: {problem}',
].join('\n');

// Pattern 2: Few-Shot with structured output
const fewShotPrompt = [
  'Classify the support ticket. Respond with JSON only.',
  '',
  'Examples:',
  'Input: "I cannot log in to my account"',
  'Output: {"category": "authentication", "priority": "high", "sentiment": "frustrated"}',
  '',
  'Input: "How do I export my data?"',
  'Output: {"category": "feature_question", "priority": "low", "sentiment": "neutral"}',
  '',
  'Now classify:',
  'Input: "{ticket_text}"',
  'Output:',
].join('\n');

// Pattern 3: System prompt with guardrails
const systemPrompt = [
  'You are a customer support assistant for Acme Corp.',
  '',
  'Rules:',
  '- Only answer questions about Acme products',
  '- Never reveal internal processes or pricing logic',
  '- If unsure, say "Let me connect you with a human agent"',
  '- Never generate code or help with programming tasks',
  '- Respond in the same language as the user',
  '',
  'Available actions: [lookup_order, check_status, create_ticket]',
].join('\n');

// Pattern 4: Self-consistency (multiple samples + majority vote)
async function selfConsistency(prompt: string, n: number = 5): Promise<string> {
  const responses = await Promise.all(
    Array.from({ length: n }, () =>
      llm.chat.completions.create({
        model: 'gpt-4o',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.7, // Higher temp for diversity
      })
    )
  );

  // Extract answers and find majority
  const answers = responses.map(r => extractAnswer(r.choices[0].message.content!));
  return majorityVote(answers);
}
```

---

## LLM Evaluation

```typescript
// Evaluation framework for RAG systems
interface EvalMetrics {
  faithfulness: number;    // Does answer match context? (no hallucination)
  relevance: number;       // Does answer address the question?
  contextRecall: number;   // Did retrieval find relevant docs?
  contextPrecision: number; // Are retrieved docs actually relevant?
}

class RAGEvaluator {
  // Faithfulness: Check if answer is grounded in context
  async evaluateFaithfulness(answer: string, context: string[]): Promise<number> {
    const response = await this.llm.chat.completions.create({
      model: 'gpt-4o',
      messages: [{
        role: 'user',
        content: [
          'Given the context and answer, identify claims in the answer.',
          'For each claim, determine if it is supported by the context.',
          'Return JSON: {"claims": [{"text": "...", "supported": true/false}]}',
          '',
          `Context: ${context.join('\n')}`,
          `Answer: ${answer}`,
        ].join('\n'),
      }],
      response_format: { type: 'json_object' },
    });

    const result = JSON.parse(response.choices[0].message.content!);
    const supported = result.claims.filter((c: any) => c.supported).length;
    return supported / result.claims.length;
  }

  // Context Recall: What fraction of ground truth is in retrieved context?
  async evaluateContextRecall(
    groundTruth: string,
    retrievedContext: string[]
  ): Promise<number> {
    const truthStatements = await this.extractStatements(groundTruth);
    let found = 0;

    for (const statement of truthStatements) {
      const isPresent = await this.isStatementInContext(statement, retrievedContext);
      if (isPresent) found++;
    }

    return found / truthStatements.length;
  }
}

// Automated test suite for prompts
interface PromptTestCase {
  input: string;
  expectedOutput?: string;        // Exact match
  expectedContains?: string[];    // Must contain these
  expectedNotContains?: string[]; // Must NOT contain these
  maxTokens?: number;             // Cost guard
  maxLatencyMs?: number;          // Performance guard
}

async function runPromptTests(
  prompt: string,
  testCases: PromptTestCase[]
): Promise<TestResults> {
  const results = await Promise.all(testCases.map(async (tc) => {
    const start = Date.now();
    const output = await generateWithPrompt(prompt, tc.input);
    const latency = Date.now() - start;

    return {
      input: tc.input,
      output,
      latency,
      passed: evaluateTestCase(output, latency, tc),
    };
  }));

  return {
    total: results.length,
    passed: results.filter(r => r.passed).length,
    failed: results.filter(r => !r.passed),
  };
}
```

---

## Cost Optimization

```typescript
// Token-aware routing: use cheapest model that works
class ModelRouter {
  private models = [
    { id: 'gpt-4o-mini', costPer1kInput: 0.00015, costPer1kOutput: 0.0006, quality: 0.7 },
    { id: 'gpt-4o', costPer1kInput: 0.0025, costPer1kOutput: 0.01, quality: 0.95 },
    { id: 'claude-3-5-sonnet', costPer1kInput: 0.003, costPer1kOutput: 0.015, quality: 0.97 },
  ];

  selectModel(task: TaskClassification): ModelConfig {
    switch (task.complexity) {
      case 'simple': return this.models[0]; // Classification, extraction
      case 'moderate': return this.models[1]; // Summarization, Q&A
      case 'complex': return this.models[2]; // Reasoning, code generation
    }
  }
}

// Caching layer for repeated queries
class SemanticCache {
  async get(query: string): Promise<CachedResponse | null> {
    const embedding = await this.embed(query);
    const similar = await this.vectorDb.search('cache', {
      vector: embedding,
      limit: 1,
      score_threshold: 0.95, // Very high similarity required
    });

    if (similar.length > 0 && !this.isExpired(similar[0])) {
      return similar[0].payload as CachedResponse;
    }
    return null;
  }

  async set(query: string, response: string): Promise<void> {
    const embedding = await this.embed(query);
    await this.vectorDb.upsert('cache', {
      points: [{
        id: crypto.randomUUID(),
        vector: embedding,
        payload: { query, response, createdAt: Date.now() },
      }],
    });
  }
}
```

---

## Guardrails

```typescript
// Input/output validation for LLM applications
class LLMGuardrails {
  // Input guardrails
  async validateInput(input: string): Promise<ValidationResult> {
    const checks = await Promise.all([
      this.checkPromptInjection(input),
      this.checkPII(input),
      this.checkToxicity(input),
      this.checkLength(input),
    ]);

    const failed = checks.filter(c => !c.passed);
    return { passed: failed.length === 0, violations: failed };
  }

  // Output guardrails
  async validateOutput(output: string, context: GuardrailContext): Promise<ValidationResult> {
    const checks = await Promise.all([
      this.checkHallucination(output, context.sources),
      this.checkPIILeakage(output),
      this.checkToxicity(output),
      this.checkOffTopic(output, context.allowedTopics),
    ]);

    const failed = checks.filter(c => !c.passed);
    return { passed: failed.length === 0, violations: failed };
  }

  private async checkPromptInjection(input: string): Promise<Check> {
    const suspiciousPatterns = [
      /ignore (all )?(previous|above) instructions/i,
      /you are now/i,
      /system prompt/i,
      /\[INST\]/i,
      /<\|im_start\|>/i,
    ];

    const hasSuspicious = suspiciousPatterns.some(p => p.test(input));
    if (hasSuspicious) {
      // Use classifier for confirmation (reduce false positives)
      const result = await this.classifyInjection(input);
      return { passed: result.score < 0.8, reason: 'Potential prompt injection' };
    }
    return { passed: true };
  }
}
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| Stuffing entire documents into context | Token waste, dilutes relevance | Chunk + retrieve only relevant sections |
| No evaluation before production | Unknown quality, silent failures | Automated eval suite with regression tests |
| Hardcoded prompts in code | Hard to iterate, no versioning | Prompt templates with version control |
| Ignoring token costs | Bills explode with scale | Model routing, caching, batching |
| No output validation | Hallucinations reach users | Guardrails + citation verification |
| Fine-tuning before trying prompting | Expensive, slow iteration | Exhaust prompting techniques first |
| Single embedding model for all | Suboptimal for different content types | Task-specific embeddings (code vs prose) |
| No chunking strategy | Chunks too big or split mid-sentence | Semantic chunking with sentence boundaries |

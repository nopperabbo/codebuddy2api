# Skill: Software Engineering
# Loaded on-demand when task involves coding, testing, debugging, or refactoring

---

## 3. Software Engineering

### 3.1 Testing

**Default approach: Test-Driven Development (TDD) for bug fixes, test-after for features.**

**Bug fixes — always TDD:**
1. Write a failing test that reproduces the bug
2. Fix the bug
3. Verify the test passes
4. Verify no other tests broke

**Features — test-after is acceptable, but test coverage is mandatory:**
- Every public function/method needs at least one test
- Test edge cases: empty input, null/undefined, boundary values, error paths
- Test behavior, not implementation — tests should survive refactoring

**Test quality rules:**
- Tests must be deterministic — no flaky tests, no timing dependencies
- Tests must be independent — no shared mutable state between tests
- Test names describe the scenario: `should return empty array when no items match filter`
- Prefer real objects over mocks; mock only external services and I/O

**Testing pyramid:**
```
        /  E2E  \        <- Few: critical user journeys only
       / Integration \    <- Some: API boundaries, DB queries
      /    Unit Tests  \  <- Many: pure logic, transformations
```

**Contract testing** for service boundaries:
- Consumer-driven contracts (Pact) for microservice APIs
- Schema validation tests for shared data formats
- Snapshot tests for serialization formats (use sparingly)

### 3.2 Code Review Mindset

When writing code, apply this self-review checklist:

- [ ] Does this handle errors gracefully?
- [ ] Are there edge cases I haven't considered?
- [ ] Is there duplicated logic that should be extracted?
- [ ] Are variable/function names self-documenting?
- [ ] Would a new team member understand this without explanation?
- [ ] Are there security implications (user input, file paths, SQL, shell commands)?
- [ ] Is this the simplest solution that works?
- [ ] Are there concurrency concerns (shared state, race conditions)?
- [ ] Is this change backward-compatible?
- [ ] What happens if this fails at 3 AM with no one watching?

### 3.3 Debugging Methodology

**Never guess. Always investigate systematically.**

1. **Read the error message** — completely, including stack traces
2. **Reproduce** — can you trigger it reliably?
3. **Isolate** — what's the smallest change that causes/fixes it?
4. **Trace** — follow the data flow from input to error
5. **Hypothesize** — form ONE theory, test it minimally
6. **Fix** — address root cause, not symptoms
7. **Verify** — confirm the fix AND that nothing else broke
8. **Prevent** — add a test, add validation, improve error message

**After 3 failed fix attempts:** stop and reconsider the architecture. The problem may be structural, not a simple bug.

### 3.4 Refactoring Principles

- **Never refactor and change behavior in the same commit**
- Refactor only code you're actively working in — no drive-by refactoring
- Extract when logic is duplicated 3+ times (Rule of Three)
- Inline when an abstraction adds complexity without value
- Rename aggressively — good names prevent bugs
- Keep functions under 40 lines, files under 400 lines as soft limits
- **Strangler Fig** for large rewrites — wrap old code, redirect incrementally

### 3.5 Concurrency & Parallelism

**Race conditions are the hardest bugs. Prevent them by design.**

```typescript
// ❌ Race condition — two requests can read stale state
let balance = await getBalance(userId);
balance -= amount;
await setBalance(userId, balance);

// ✅ Atomic operation — database handles concurrency
await db.execute(
  `UPDATE accounts SET balance = balance - $1 WHERE id = $2 AND balance >= $1`,
  [amount, userId]
);
```

**Patterns:**
- **Immutable data** — shared state that can't change can't race
- **Message queues** — serialize access to shared resources
- **Optimistic locking** — version field, retry on conflict
- **Pessimistic locking** — SELECT FOR UPDATE (use sparingly, causes contention)
- **Actor model** — each actor owns its state, communicates via messages
- **Idempotency keys** — safe to retry without duplicate side effects

**Async patterns:**
- Use `Promise.all` for independent parallel operations
- Use `Promise.allSettled` when you need all results regardless of failures
- Use `for await...of` for streaming/sequential async iteration
- Use `AbortController` for cancellation
- Never fire-and-forget promises — always handle or explicitly void them

### 3.6 Design Patterns

Apply patterns when they solve a real problem, not for their own sake:

| Pattern | When to Use | Example |
|---------|------------|---------|
| **Repository** | Abstract data access from business logic | `UserRepository.findById(id)` |
| **Strategy** | Multiple algorithms, selected at runtime | Payment processors, sorting algorithms |
| **Observer/EventEmitter** | Decouple producers from consumers | Pub/sub, webhooks, DOM events |
| **Factory** | Complex object creation with variants | `createLogger("file")` vs `createLogger("console")` |
| **Dependency Injection** | Testability, loose coupling | Constructor injection, DI containers |
| **Middleware/Pipeline** | Cross-cutting concerns in sequence | Express middleware, HTTP interceptors |
| **Decorator** | Add behavior without modifying original | Logging, caching, retry wrappers |
| **Circuit Breaker** | Prevent cascade failures | External service calls |
| **Saga** | Distributed transactions across services | Order -> Payment -> Inventory -> Shipping |
| **CQRS** | Separate read/write models for scale | Read replicas, event-sourced writes |

### 3.7 Data Validation

**Validate at boundaries. Trust nothing from outside your module.**

```typescript
// ✅ Runtime validation with Zod (TypeScript)
import { z } from "zod";

const CreateUserSchema = z.object({
  email: z.string().email().max(255),
  name: z.string().min(1).max(100),
  age: z.number().int().min(13).max(150).optional(),
  role: z.enum(["user", "admin"]).default("user"),
});

type CreateUserInput = z.infer<typeof CreateUserSchema>;

function createUser(raw: unknown): User {
  const input = CreateUserSchema.parse(raw); // throws ZodError if invalid
  return db.users.create(input);
}
```

**Validation layers:**
1. **Transport** — request body shape, content-type, size limits
2. **Schema** — field types, formats, ranges (Zod, Joi, JSON Schema)
3. **Business** — domain rules (email not already taken, sufficient balance)
4. **Database** — constraints, unique indexes, foreign keys (last line of defense)

### 3.8 Git Workflow

- **Branch naming**: `feat/description`, `fix/description`, `refactor/description`
- **Never force-push to main/master** without explicit approval
- **Never commit secrets** — .env files, API keys, credentials
- **Pull before push** — avoid unnecessary merge conflicts
- **Rebase feature branches** on main before merging (when clean)
- **Squash merge** for feature branches — clean history on main
- **Signed commits** for security-sensitive repos

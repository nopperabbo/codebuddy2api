# Skill: Advanced Patterns & Principles
# Loaded on-demand when task involves 12-Factor App, SOLID, performance engineering, file handling, or feature flags

---

## 12.1 Twelve-Factor App

1. **Codebase** — one repo per app, many deploys
2. **Dependencies** — explicitly declare and isolate
3. **Config** — store in environment, not code
4. **Backing services** — treat as attached resources
5. **Build, release, run** — strictly separate stages
6. **Processes** — stateless, share-nothing
7. **Port binding** — export services via port
8. **Concurrency** — scale via process model
9. **Disposability** — fast startup, graceful shutdown
10. **Dev/prod parity** — keep environments similar
11. **Logs** — treat as event streams
12. **Admin processes** — run as one-off processes

---

## 12.2 SOLID Principles

- **S**ingle Responsibility — one reason to change
- **O**pen/Closed — open for extension, closed for modification
- **L**iskov Substitution — subtypes must be substitutable
- **I**nterface Segregation — many specific interfaces over one general
- **D**ependency Inversion — depend on abstractions, not concretions

---

## 12.3 Performance Engineering

**Measure first, optimize second. Never optimize without profiling.**

```
1. Define performance budget (LCP < 2.5s, API p99 < 500ms)
2. Measure current state (profiler, APM, lighthouse)
3. Identify bottleneck (CPU? Memory? I/O? Network?)
4. Hypothesize fix
5. Implement smallest change
6. Measure again — did it improve?
7. Repeat until budget met
```

**Common bottlenecks and fixes:**
| Bottleneck | Diagnosis | Fix |
|-----------|-----------|-----|
| N+1 queries | Slow page with many DB calls | DataLoader, JOINs, eager loading |
| Memory leak | Growing memory over time | Heap snapshot, weak references |
| CPU-bound | High CPU, slow responses | Worker threads, caching, algorithm |
| Connection exhaustion | Timeouts under load | Connection pooling, backpressure |
| Large payloads | Slow transfers | Pagination, compression, streaming |
| Cold starts | First request slow | Keep-alive, pre-warming, smaller bundles |

---

## 12.4 File Handling & Streaming

```typescript
// ✅ Stream large files — don't load into memory
import { pipeline } from "node:stream/promises";
import { createReadStream, createWriteStream } from "node:fs";
import { createGzip } from "node:zlib";

await pipeline(
  createReadStream("large-file.csv"),
  createGzip(),
  createWriteStream("large-file.csv.gz")
);

// ✅ Presigned URLs for file uploads (S3)
const url = await s3.getSignedUrl("putObject", {
  Bucket: "uploads",
  Key: `${userId}/${filename}`,
  ContentType: mimeType,
  Expires: 300, // 5 minutes
});
// Client uploads directly to S3, bypassing your server
```

---

## 12.5 Feature Flags

```typescript
// Pattern: feature flag service
const flags = await featureFlags.evaluate(userId);

if (flags.isEnabled("new-checkout-flow")) {
  return renderNewCheckout();
} else {
  return renderLegacyCheckout();
}

// Lifecycle: create → enable for team → canary 5% → ramp to 100% → remove flag + old code
// IMPORTANT: Remove flags after full rollout — flag debt is real tech debt
```

# Skill: Architecture Advanced
# Loaded on-demand when task involves system design, API design, database selection, caching, scaling, or error handling

## Auto-Detect

Trigger this skill when:
- Task mentions: API design, system design, database choice, scaling, microservices
- Files: `docker-compose.yml`, `schema.prisma`, `*.proto`, `openapi.yaml`
- Patterns: service boundaries, data modeling, caching strategy, queue setup
- `package.json` contains: `@trpc/server`, `graphql`, `@nestjs/microservices`, `bullmq`

---

## Decision Tree: API Style

```
What are you building?
├── Internal tool / full-stack app (same team owns client + server)?
│   └── tRPC — end-to-end type safety, zero codegen, fastest DX
├── Public API consumed by third parties?
│   └── REST + OpenAPI spec — universal, cacheable, well-understood
├── Complex data with nested relationships (social, e-commerce)?
│   ├── Clients need flexible queries? → GraphQL
│   └── Server controls all queries? → REST with includes/sparse fieldsets
├── High-performance internal service-to-service?
│   └── gRPC — binary protocol, streaming, code generation
├── Real-time bidirectional?
│   └── WebSocket (or Socket.IO for fallback)
└── One-way server push (notifications, feeds)?
    └── Server-Sent Events (SSE) — simpler than WebSocket
```

## Decision Tree: Database Selection

```
What's your data shape?
├── Structured, relational, needs ACID transactions?
│   ├── General purpose → PostgreSQL (always the safe default)
│   ├── Simple/embedded → SQLite (single-server, edge, mobile)
│   └── MySQL ecosystem required → MySQL 8+ / PlanetScale
├── Document-oriented, flexible schema?
│   └── MongoDB (but consider: do you REALLY need schemaless?)
├── Key-value, high throughput, caching?
│   └── Redis / Valkey / DragonflyDB
├── Time-series data (metrics, IoT, logs)?
│   └── TimescaleDB (Postgres extension) or ClickHouse
├── Full-text search?
│   └── PostgreSQL full-text (simple) or Elasticsearch/Meilisearch (complex)
├── Graph relationships (social networks, recommendations)?
│   └── Neo4j or PostgreSQL with recursive CTEs
└── Vector embeddings (AI/ML, semantic search)?
    └── pgvector (Postgres) or Pinecone/Qdrant
```

## Decision Tree: Scaling

```
Performance problem identified?
├── Reads are slow?
│   ├── Add indexes (EXPLAIN ANALYZE first) → 90% of cases
│   ├── Add caching layer (Redis) → frequently accessed, rarely changed
│   ├── Read replicas → read-heavy workload
│   └── CDN → static/semi-static content
├── Writes are slow?
│   ├── Batch writes → bulk inserts
│   ├── Async processing (queue) → non-critical writes
│   ├── Connection pooling → pool exhaustion
│   └── Vertical scaling → bigger machine (cheapest solution)
├── Single service overloaded?
│   ├── Horizontal scaling (stateless) → add more instances
│   ├── Extract hot path to separate service → targeted scaling
│   └── Rate limiting → protect from abuse
└── Database is the bottleneck?
    ├── Query optimization → always first
    ├── CQRS → separate read/write models
    ├── Sharding → last resort, massive complexity
    └── Polyglot persistence → right DB for each use case
```

---

## API Design Patterns

### REST Best Practices
```yaml
# Resource naming
GET    /api/v1/users          # List (paginated)
POST   /api/v1/users          # Create
GET    /api/v1/users/:id      # Read
PUT    /api/v1/users/:id      # Replace
PATCH  /api/v1/users/:id      # Partial update
DELETE /api/v1/users/:id      # Delete

# Relationships
GET    /api/v1/users/:id/orders        # User's orders
POST   /api/v1/users/:id/orders        # Create order for user

# Filtering, sorting, pagination
GET    /api/v1/orders?status=pending&sort=-createdAt&page=2&limit=20

# Status codes
200 OK, 201 Created, 204 No Content
400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found
409 Conflict, 422 Unprocessable Entity, 429 Too Many Requests
500 Internal Server Error, 503 Service Unavailable
```

### tRPC Pattern
```typescript
import { initTRPC } from '@trpc/server';
import { z } from 'zod';

const t = initTRPC.context<Context>().create();

export const appRouter = t.router({
  user: t.router({
    getById: t.procedure
      .input(z.object({ id: z.string().uuid() }))
      .query(async ({ input, ctx }) => {
        return ctx.db.user.findUniqueOrThrow({ where: { id: input.id } });
      }),
    create: t.procedure
      .input(z.object({ email: z.string().email(), name: z.string() }))
      .mutation(async ({ input, ctx }) => {
        return ctx.db.user.create({ data: input });
      }),
  }),
});
```

---

## Caching Strategy

```
Cache Decision:
├── Data changes rarely, read often? → Cache with long TTL (1h+)
├── Data changes often but stale is OK for seconds? → Cache with short TTL (30s-5min)
├── Data MUST be fresh? → No cache, or cache-aside with event invalidation
├── Expensive computation? → Cache result with TTL
└── Per-user data? → Cache with user-scoped key

Cache Layers:
1. Browser cache (Cache-Control headers) — static assets
2. CDN (Cloudflare, Vercel Edge) — public pages, API responses
3. Application cache (Redis) — computed data, sessions, rate limits
4. Database query cache — query results (use cautiously)
```

```typescript
// Cache-aside pattern
async function getUser(id: string): Promise<User> {
  const cached = await redis.get(`user:${id}`);
  if (cached) return JSON.parse(cached);

  const user = await db.user.findUnique({ where: { id } });
  if (user) await redis.setex(`user:${id}`, 300, JSON.stringify(user)); // 5min TTL
  return user;
}

// Invalidation on write
async function updateUser(id: string, data: Partial<User>) {
  const user = await db.user.update({ where: { id }, data });
  await redis.del(`user:${id}`); // Invalidate cache
  return user;
}
```

---

## Error Handling Patterns

```typescript
// Typed application errors
class AppError extends Error {
  constructor(
    public code: string,
    public statusCode: number,
    message: string,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'AppError';
  }

  static notFound(resource: string, id: string) {
    return new AppError('NOT_FOUND', 404, `${resource} ${id} not found`);
  }
  static unauthorized(reason: string) {
    return new AppError('UNAUTHORIZED', 401, reason);
  }
  static conflict(message: string) {
    return new AppError('CONFLICT', 409, message);
  }
  static validation(details: Record<string, string>) {
    return new AppError('VALIDATION_ERROR', 422, 'Validation failed', details);
  }
}

// Global error handler (Express)
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  if (err instanceof AppError) {
    return res.status(err.statusCode).json({
      error: { code: err.code, message: err.message, details: err.details }
    });
  }
  // Unknown error — log full details, return generic message
  logger.error('Unhandled error', { err, path: req.path });
  res.status(500).json({ error: { code: 'INTERNAL', message: 'Something went wrong' } });
});
```

---

## 12-Factor App Checklist

| Factor | Requirement | Check |
|--------|-------------|-------|
| 1. Codebase | One repo per app, many deploys | Single source of truth |
| 2. Dependencies | Explicitly declared (package.json/go.mod) | No implicit system deps |
| 3. Config | Env vars, not hardcoded | `process.env`, validated at startup |
| 4. Backing Services | Treat as attached resources | Connection strings in env |
| 5. Build/Release/Run | Strict separation | CI builds, CD deploys |
| 6. Processes | Stateless, share-nothing | No local file storage for state |
| 7. Port Binding | Self-contained, export via port | `app.listen(PORT)` |
| 8. Concurrency | Scale via process model | Horizontal scaling, no shared memory |
| 9. Disposability | Fast startup, graceful shutdown | Handle SIGTERM, drain connections |
| 10. Dev/Prod Parity | Keep environments similar | Same DB, same services |
| 11. Logs | Treat as event streams | stdout/stderr, collected externally |
| 12. Admin Processes | Run as one-off tasks | Migrations, scripts via CLI |

---

## Anti-Patterns

| ❌ Don't | ✅ Do Instead |
|----------|---------------|
| Microservices from day one | Monolith → modular monolith → extract when needed |
| Shared database between services | Each service owns its data, communicate via APIs/events |
| N+1 queries in loops | Batch loading, DataLoader, eager loading |
| Caching without invalidation strategy | Define TTL + invalidation triggers before caching |
| Synchronous calls for non-critical paths | Queue/event for emails, notifications, analytics |
| Generic error messages ("Something went wrong") | Typed errors with codes, actionable messages |
| Premature optimization | Measure first (EXPLAIN, profiler), optimize bottlenecks |
| God services (one service does everything) | Single responsibility, bounded contexts |
| Distributed transactions across services | Saga pattern with compensating actions |
| Ignoring backpressure | Rate limiting, circuit breakers, queue depth limits |

---

## Verification Checklist

Before considering architecture work done:
- [ ] API endpoints follow consistent naming and HTTP method conventions
- [ ] All endpoints have input validation (schema-based)
- [ ] Error responses are structured and typed (code + message + details)
- [ ] Database queries are optimized (EXPLAIN ANALYZE on critical paths)
- [ ] Caching strategy defined with clear invalidation rules
- [ ] Rate limiting on public endpoints
- [ ] Health check endpoint exists (`/health` or `/healthz`)
- [ ] Graceful shutdown handles in-flight requests
- [ ] Idempotency keys for non-idempotent operations
- [ ] Pagination on all list endpoints (cursor-based preferred)
- [ ] API versioning strategy defined
- [ ] Logging is structured (JSON) with correlation IDs

---

## MCP Integration

| Tool | Use For |
|------|---------|
| `context7` | Look up framework-specific patterns (tRPC, Prisma, etc.) |
| `sequential-thinking` | System design decisions, trade-off analysis |
| `grep` | Find N+1 queries, missing error handling, raw SQL |
| `bash` | Run database migrations, test API endpoints with curl |
| `playwright` | Integration testing of API flows |

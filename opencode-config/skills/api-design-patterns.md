# Skill: API Design Patterns
# Loaded on-demand when task involves REST, GraphQL, gRPC, API versioning, pagination, rate limiting, or OpenAPI

## Auto-Detect

Trigger this skill when:
- Task mentions: REST, GraphQL, gRPC, API design, pagination, rate limiting, OpenAPI
- Files: `openapi.yaml`, `*.proto`, `schema.graphql`, `routes/`, `resolvers/`
- Patterns: endpoint design, request/response format, API versioning
- `package.json` contains: `express`, `fastify`, `@nestjs/core`, `graphql`, `@grpc/grpc-js`

---

## Decision Tree: API Style

```
What are you building?
+-- Internal tool / full-stack app (same team)?
|   +-- tRPC (end-to-end type safety, zero codegen)
+-- Public API for third parties?
|   +-- REST + OpenAPI spec (universal, cacheable)
+-- Complex nested data (social, e-commerce)?
|   +-- Clients need flexible queries? -> GraphQL
|   +-- Server controls queries? -> REST with includes/sparse fieldsets
+-- High-performance service-to-service?
|   +-- gRPC (binary, streaming, code generation)
+-- Real-time bidirectional?
|   +-- WebSocket or gRPC streaming
+-- One-way server push?
    +-- Server-Sent Events (SSE)
```

---

## REST Maturity Model (Richardson)

```
Level 0: Single endpoint, POST everything
  POST /api { "action": "getUser", "id": 123 }
  -> This is RPC over HTTP, not REST

Level 1: Resources (nouns, not verbs)
  GET /users/123
  POST /orders
  -> Proper resource modeling

Level 2: HTTP verbs + status codes
  GET    /users/123     -> 200 OK
  POST   /users         -> 201 Created
  PUT    /users/123     -> 200 OK
  PATCH  /users/123     -> 200 OK
  DELETE /users/123     -> 204 No Content
  -> Proper use of HTTP semantics

Level 3: HATEOAS (Hypermedia)
  GET /users/123
  {
    "id": 123,
    "name": "Alice",
    "_links": {
      "self": { "href": "/users/123" },
      "orders": { "href": "/users/123/orders" },
      "update": { "href": "/users/123", "method": "PATCH" }
    }
  }
  -> Discoverable API (rarely needed in practice)
```

### REST Best Practices

```typescript
// Resource naming conventions
// GOOD:
GET    /users                    // List users
GET    /users/123                // Get user
POST   /users                    // Create user
PATCH  /users/123                // Partial update
PUT    /users/123                // Full replace
DELETE /users/123                // Delete user
GET    /users/123/orders         // User's orders (sub-resource)
POST   /users/123/orders         // Create order for user

// BAD:
GET    /getUsers                 // Verb in URL
POST   /createUser               // Verb in URL
GET    /users/123/getOrders      // Verb in URL
DELETE /users/delete/123         // Verb in URL

// Filtering, sorting, pagination via query params
GET /users?status=active&sort=-created_at&page=2&limit=20
GET /orders?filter[status]=pending&filter[total_gte]=100&include=items,customer

// Status codes
200 OK           // Successful GET, PUT, PATCH
201 Created      // Successful POST (include Location header)
204 No Content   // Successful DELETE
400 Bad Request  // Validation error (include details)
401 Unauthorized // Missing/invalid authentication
403 Forbidden    // Authenticated but not authorized
404 Not Found    // Resource doesn't exist
409 Conflict     // Duplicate, version conflict
422 Unprocessable // Semantic validation error
429 Too Many Req // Rate limited (include Retry-After header)
500 Internal     // Server error (never expose internals)
```

---

## Error Response Format

```typescript
// Consistent error format (RFC 7807 Problem Details)
interface ProblemDetail {
  type: string;        // URI reference identifying the problem type
  title: string;       // Short human-readable summary
  status: number;      // HTTP status code
  detail: string;      // Human-readable explanation
  instance: string;    // URI of the specific occurrence
  errors?: {           // Validation errors
    field: string;
    message: string;
    code: string;
  }[];
}

// Example responses:
// 400 Bad Request
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "The request body contains invalid fields",
  "instance": "/users",
  "errors": [
    { "field": "email", "message": "Must be a valid email address", "code": "INVALID_FORMAT" },
    { "field": "age", "message": "Must be at least 18", "code": "MIN_VALUE" }
  ]
}

// 429 Too Many Requests
{
  "type": "https://api.example.com/errors/rate-limit",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "You have exceeded 100 requests per minute",
  "instance": "/users"
}
// Headers: Retry-After: 30, X-RateLimit-Limit: 100, X-RateLimit-Remaining: 0
```

---

## Pagination Patterns

```typescript
// Pattern 1: Offset-based (simple, but has issues with large datasets)
// GET /users?page=3&limit=20
interface OffsetPaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
    hasNext: boolean;
    hasPrev: boolean;
  };
}

// Pattern 2: Cursor-based (recommended for large/real-time datasets)
// GET /users?cursor=eyJpZCI6MTIzfQ&limit=20
interface CursorPaginatedResponse<T> {
  data: T[];
  pagination: {
    cursor: string | null;  // Opaque cursor for next page
    hasMore: boolean;
    limit: number;
  };
}

// Implementation
async function cursorPaginate<T>(
  query: QueryBuilder,
  cursor: string | null,
  limit: number
): Promise<CursorPaginatedResponse<T>> {
  // Decode cursor
  const decoded = cursor ? JSON.parse(Buffer.from(cursor, 'base64url').toString()) : null;

  // Fetch one extra to determine hasMore
  const items = await query
    .where(decoded ? { id: { gt: decoded.id } } : {})
    .orderBy({ id: 'asc' })
    .limit(limit + 1)
    .execute();

  const hasMore = items.length > limit;
  const data = items.slice(0, limit);

  // Encode next cursor
  const nextCursor = hasMore
    ? Buffer.from(JSON.stringify({ id: data[data.length - 1].id })).toString('base64url')
    : null;

  return { data, pagination: { cursor: nextCursor, hasMore, limit } };
}

// Pattern 3: Keyset pagination (for sorted results)
// GET /users?after_id=123&limit=20
// Most performant for large datasets (uses index scan)
```

### When to Use Which

```
+-- Small dataset (< 10K records)? -> Offset (simple, supports "jump to page")
+-- Large dataset, sequential access? -> Cursor (consistent, no skipping)
+-- Real-time feed (new items added)? -> Cursor (no duplicate/missing items)
+-- Need "page 47 of 200"? -> Offset (cursor can't jump)
+-- Sorted by non-unique field? -> Keyset with tiebreaker (id)
```

---

## Rate Limiting

```typescript
// Token bucket algorithm (most common)
class TokenBucketRateLimiter {
  constructor(
    private readonly store: Redis,
    private readonly config: {
      maxTokens: number;      // Bucket capacity (burst limit)
      refillRate: number;     // Tokens per second
      keyPrefix: string;
    }
  ) {}

  async consume(key: string, tokens: number = 1): Promise<RateLimitResult> {
    const bucketKey = `${this.config.keyPrefix}:${key}`;
    const now = Date.now();

    // Atomic operation with Lua script
    const result = await this.store.eval(`
      local key = KEYS[1]
      local max_tokens = tonumber(ARGV[1])
      local refill_rate = tonumber(ARGV[2])
      local now = tonumber(ARGV[3])
      local requested = tonumber(ARGV[4])

      local bucket = redis.call('hmget', key, 'tokens', 'last_refill')
      local tokens = tonumber(bucket[1]) or max_tokens
      local last_refill = tonumber(bucket[2]) or now

      -- Refill tokens
      local elapsed = (now - last_refill) / 1000
      tokens = math.min(max_tokens, tokens + elapsed * refill_rate)

      -- Try to consume
      if tokens >= requested then
        tokens = tokens - requested
        redis.call('hmset', key, 'tokens', tokens, 'last_refill', now)
        redis.call('expire', key, math.ceil(max_tokens / refill_rate) * 2)
        return {1, tokens, max_tokens}
      else
        redis.call('hmset', key, 'tokens', tokens, 'last_refill', now)
        return {0, tokens, max_tokens}
      end
    `, 1, bucketKey, this.config.maxTokens, this.config.refillRate, now, tokens);

    const [allowed, remaining, limit] = result as number[];
    return {
      allowed: allowed === 1,
      remaining: Math.floor(remaining),
      limit,
      retryAfter: allowed ? 0 : Math.ceil((tokens - remaining) / this.config.refillRate),
    };
  }
}

// Middleware
function rateLimitMiddleware(limiter: TokenBucketRateLimiter) {
  return async (req: Request, res: Response, next: NextFunction) => {
    const key = req.user?.id || req.ip; // Per-user or per-IP
    const result = await limiter.consume(key);

    // Always set rate limit headers
    res.setHeader('X-RateLimit-Limit', result.limit);
    res.setHeader('X-RateLimit-Remaining', result.remaining);

    if (!result.allowed) {
      res.setHeader('Retry-After', result.retryAfter);
      return res.status(429).json({
        type: 'https://api.example.com/errors/rate-limit',
        title: 'Rate Limit Exceeded',
        status: 429,
        detail: `Rate limit exceeded. Retry after ${result.retryAfter} seconds.`,
      });
    }

    next();
  };
}
```

---

## GraphQL Schema Design

```graphql
# schema.graphql

# Use interfaces for shared fields
interface Node {
  id: ID!
}

interface Timestamped {
  createdAt: DateTime!
  updatedAt: DateTime!
}

type User implements Node & Timestamped {
  id: ID!
  email: String!
  name: String!
  orders(first: Int, after: String): OrderConnection!
  createdAt: DateTime!
  updatedAt: DateTime!
}

# Relay-style pagination (cursor-based)
type OrderConnection {
  edges: [OrderEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type OrderEdge {
  node: Order!
  cursor: String!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}

type Order implements Node & Timestamped {
  id: ID!
  status: OrderStatus!
  total: Money!
  items: [OrderItem!]!
  createdAt: DateTime!
  updatedAt: DateTime!
}

# Custom scalars for domain types
scalar DateTime
scalar Money

enum OrderStatus {
  PENDING
  CONFIRMED
  SHIPPED
  DELIVERED
  CANCELLED
}

# Input types for mutations
input CreateOrderInput {
  items: [OrderItemInput!]!
  shippingAddress: AddressInput!
}

# Mutation responses include errors
type CreateOrderPayload {
  order: Order
  errors: [UserError!]!
}

type UserError {
  field: [String!]
  message: String!
  code: ErrorCode!
}

type Mutation {
  createOrder(input: CreateOrderInput!): CreateOrderPayload!
}

type Query {
  user(id: ID!): User
  orders(
    first: Int
    after: String
    filter: OrderFilterInput
  ): OrderConnection!
}
```

---

## API Versioning

```
Strategy 1: URL path versioning (most common)
  GET /v1/users/123
  GET /v2/users/123
  + Simple, explicit, easy to route
  - URL changes, breaks bookmarks

Strategy 2: Header versioning
  GET /users/123
  Accept: application/vnd.api+json;version=2
  + Clean URLs
  - Hidden, harder to test

Strategy 3: Query parameter
  GET /users/123?version=2
  + Easy to test
  - Pollutes query string

Recommendation: URL path versioning for public APIs
  - Only increment major version for breaking changes
  - Support N-1 version minimum
  - Deprecation timeline: announce 6 months, sunset 12 months
```

---

## OpenAPI Specification

```yaml
# openapi.yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
  description: API for managing orders
  contact:
    email: api-support@example.com

servers:
  - url: https://api.example.com/v1
    description: Production
  - url: https://api-staging.example.com/v1
    description: Staging

paths:
  /orders:
    get:
      operationId: listOrders
      summary: List orders
      tags: [Orders]
      parameters:
        - name: status
          in: query
          schema:
            $ref: '#/components/schemas/OrderStatus'
        - $ref: '#/components/parameters/CursorParam'
        - $ref: '#/components/parameters/LimitParam'
      responses:
        '200':
          description: Paginated list of orders
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderListResponse'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '429':
          $ref: '#/components/responses/RateLimited'

components:
  schemas:
    Order:
      type: object
      required: [id, status, total, createdAt]
      properties:
        id:
          type: string
          format: uuid
        status:
          $ref: '#/components/schemas/OrderStatus'
        total:
          type: number
          format: decimal
        createdAt:
          type: string
          format: date-time

  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - bearerAuth: []
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| Verbs in URLs | `/getUsers`, `/createOrder` | Use HTTP methods: `GET /users`, `POST /orders` |
| Inconsistent naming | `/users`, `/order-items`, `/ProductList` | Pick one convention (kebab-case) and stick to it |
| No pagination | Returns 10K records, crashes clients | Always paginate list endpoints |
| Exposing internal IDs | Sequential IDs leak data (user count) | Use UUIDs or opaque IDs |
| No rate limiting | DDoS, abuse, runaway scripts | Token bucket per user/IP |
| Breaking changes without versioning | Clients break silently | Semantic versioning, deprecation headers |
| N+1 in GraphQL resolvers | 100 users = 100 DB queries | DataLoader for batching |
| No error format standard | Every endpoint returns different errors | RFC 7807 Problem Details |

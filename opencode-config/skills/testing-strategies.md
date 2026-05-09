# Skill: Testing Strategies
# Loaded on-demand when task involves property-based testing, mutation testing, contract testing, visual regression, or load testing

## Auto-Detect

Trigger this skill when:
- Task mentions: property-based testing, mutation testing, contract testing, visual regression, load testing
- Files: `*.test.ts`, `*.spec.ts`, `*.pact.ts`, `k6/`, `*.stories.tsx`
- Patterns: test architecture, fixtures, factories, test doubles
- `package.json` contains: `fast-check`, `@pact-foundation/pact`, `stryker-mutator`, `@chromatic-com/storybook`

---

## Decision Tree: Testing Strategy

```
What are you testing?
+-- Pure business logic (no I/O)?
|   +-- Unit tests + property-based tests
+-- API endpoints?
|   +-- Integration tests (real DB, test containers)
|   +-- Contract tests (if consumed by other services)
+-- UI components?
|   +-- Component tests (Testing Library)
|   +-- Visual regression (Chromatic/Percy)
|   +-- Interaction tests (Storybook play functions)
+-- Service-to-service communication?
|   +-- Contract tests (Pact)
+-- Performance requirements?
|   +-- Load tests (k6/Gatling)
|   +-- Benchmark tests (in CI, fail on regression)
+-- Confidence in test suite quality?
    +-- Mutation testing (Stryker)
```

## Testing Pyramid (Practical)

```
        /  E2E  \          Few (5-10): Critical user journeys
       /  Visual  \        Per component: Catch CSS regressions
      / Integration \      Per feature: Real DB, real HTTP
     /   Component   \     Per component: Render + interact
    /  Unit + Property  \  Many: Pure logic, edge cases
   /____________________\

Rule of thumb:
- 70% unit/property tests (fast, cheap, many)
- 20% integration tests (slower, fewer)
- 10% E2E tests (slowest, critical paths only)
```

---

## Property-Based Testing

```typescript
import fc from 'fast-check';

// Instead of testing specific examples, test PROPERTIES that must always hold

// Property 1: Encode then decode is identity
describe('URL encoding', () => {
  it('roundtrips any string', () => {
    fc.assert(
      fc.property(fc.string(), (input) => {
        expect(decodeURIComponent(encodeURIComponent(input))).toBe(input);
      })
    );
  });
});

// Property 2: Sort is idempotent
describe('sorting', () => {
  it('sorting twice gives same result as sorting once', () => {
    fc.assert(
      fc.property(fc.array(fc.integer()), (arr) => {
        const sortedOnce = [...arr].sort((a, b) => a - b);
        const sortedTwice = [...sortedOnce].sort((a, b) => a - b);
        expect(sortedTwice).toEqual(sortedOnce);
      })
    );
  });

  it('preserves all elements', () => {
    fc.assert(
      fc.property(fc.array(fc.integer()), (arr) => {
        const sorted = [...arr].sort((a, b) => a - b);
        expect(sorted.length).toBe(arr.length);
        expect(sorted.sort()).toEqual([...arr].sort());
      })
    );
  });
});

// Property 3: Business rule invariants
describe('pricing', () => {
  it('discount never exceeds original price', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0.01, max: 10000, noNaN: true }),
        fc.float({ min: 0, max: 100, noNaN: true }),
        (price, discountPercent) => {
          const discounted = applyDiscount(price, discountPercent);
          expect(discounted).toBeGreaterThanOrEqual(0);
          expect(discounted).toBeLessThanOrEqual(price);
        }
      )
    );
  });

  it('total equals sum of line items', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            price: fc.float({ min: 0.01, max: 1000, noNaN: true }),
            quantity: fc.integer({ min: 1, max: 100 }),
          }),
          { minLength: 1, maxLength: 50 }
        ),
        (items) => {
          const order = createOrder(items);
          const expectedTotal = items.reduce((sum, i) => sum + i.price * i.quantity, 0);
          expect(order.total).toBeCloseTo(expectedTotal, 2);
        }
      )
    );
  });
});

// Custom arbitraries for domain objects
const emailArbitrary = fc.tuple(
  fc.stringOf(fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789'.split('')), { minLength: 1, maxLength: 20 }),
  fc.constantFrom('gmail.com', 'example.com', 'test.org')
).map(([local, domain]) => `${local}@${domain}`);

const userArbitrary = fc.record({
  name: fc.string({ minLength: 1, maxLength: 100 }),
  email: emailArbitrary,
  age: fc.integer({ min: 0, max: 150 }),
});
```

---

## Mutation Testing

```typescript
// Mutation testing: verify your tests actually catch bugs
// Stryker modifies your code and checks if tests fail

// stryker.config.mjs
export default {
  mutator: {
    plugins: ['@stryker-mutator/typescript-checker'],
    excludedMutations: [
      'StringLiteral', // Skip string mutations (noisy)
    ],
  },
  packageManager: 'pnpm',
  reporters: ['html', 'clear-text', 'progress'],
  testRunner: 'vitest',
  vitest: {
    configFile: 'vitest.config.ts',
  },
  coverageAnalysis: 'perTest',
  thresholds: {
    high: 80,
    low: 60,
    break: 50, // Fail CI if mutation score < 50%
  },
  // Only mutate source files, not tests
  mutate: ['src/**/*.ts', '!src/**/*.test.ts', '!src/**/*.spec.ts'],
};

// What Stryker does:
// 1. Parses your code
// 2. Creates "mutants" (small changes):
//    - a > b  ->  a >= b  (boundary mutation)
//    - a + b  ->  a - b   (arithmetic mutation)
//    - if (x)  ->  if (!x) (conditional mutation)
//    - return x  ->  return undefined (return mutation)
// 3. Runs your tests against each mutant
// 4. Reports:
//    - Killed: test caught the mutation (good!)
//    - Survived: no test caught it (your tests are weak here)
//    - Timeout: mutation caused infinite loop
//    - No coverage: no test covers this code

// Interpreting results:
// Mutation Score = killed / (killed + survived)
// Target: > 80% for critical business logic
// Focus on survived mutants in critical paths
```

---

## Contract Testing (Pact)

```typescript
// Consumer-driven contract testing
// Consumer defines expectations, provider verifies

// CONSUMER SIDE (frontend or calling service)
import { PactV3, MatchersV3 } from '@pact-foundation/pact';

const { like, eachLike, string, integer, datetime } = MatchersV3;

const provider = new PactV3({
  consumer: 'OrderWebApp',
  provider: 'OrderAPI',
  dir: './pacts',
});

describe('Order API Contract', () => {
  it('returns a list of orders', async () => {
    // Define expected interaction
    await provider
      .given('user has orders')
      .uponReceiving('a request for user orders')
      .withRequest({
        method: 'GET',
        path: '/api/orders',
        headers: { Authorization: string('Bearer token123') },
        query: { status: 'active' },
      })
      .willRespondWith({
        status: 200,
        headers: { 'Content-Type': 'application/json' },
        body: {
          data: eachLike({
            id: string('ord-123'),
            status: string('active'),
            total: like(99.99),
            createdAt: datetime("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"),
            items: eachLike({
              productId: string('prod-1'),
              quantity: integer(2),
              price: like(49.99),
            }),
          }),
          pagination: {
            cursor: string('eyJpZCI6MTIzfQ'),
            hasMore: like(true),
          },
        },
      });

    // Execute test against mock provider
    await provider.executeTest(async (mockServer) => {
      const client = new OrderClient(mockServer.url);
      const result = await client.getOrders({ status: 'active' });

      expect(result.data).toHaveLength(1);
      expect(result.data[0]).toHaveProperty('id');
      expect(result.data[0]).toHaveProperty('status', 'active');
    });
  });
});

// PROVIDER SIDE (API service)
import { Verifier } from '@pact-foundation/pact';

describe('Pact Verification', () => {
  it('validates the OrderWebApp contract', async () => {
    const verifier = new Verifier({
      providerBaseUrl: 'http://localhost:3000',
      pactUrls: ['./pacts/OrderWebApp-OrderAPI.json'],
      // Or from Pact Broker:
      // pactBrokerUrl: 'https://pact-broker.example.com',
      // providerVersion: process.env.GIT_SHA,
      stateHandlers: {
        'user has orders': async () => {
          // Set up test data
          await db.orders.create({
            data: { userId: 'test-user', status: 'active', total: 99.99 },
          });
        },
      },
    });

    await verifier.verifyProvider();
  });
});
```

---

## Visual Regression Testing

```typescript
// With Chromatic (Storybook-based)
// 1. Write stories (already done for design system)
// 2. Chromatic captures screenshots
// 3. Compares against baseline
// 4. Flags visual changes for review

// CI integration
// npx chromatic --project-token=$CHROMATIC_TOKEN

// With Playwright (for full pages)
import { test, expect } from '@playwright/test';

test('homepage visual regression', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // Full page screenshot comparison
  await expect(page).toHaveScreenshot('homepage.png', {
    maxDiffPixelRatio: 0.01, // Allow 1% pixel difference
    animations: 'disabled',   // Freeze animations
  });
});

test('responsive visual regression', async ({ page }) => {
  // Test multiple viewports
  const viewports = [
    { width: 375, height: 667, name: 'mobile' },
    { width: 768, height: 1024, name: 'tablet' },
    { width: 1440, height: 900, name: 'desktop' },
  ];

  for (const vp of viewports) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/dashboard');
    await expect(page).toHaveScreenshot(`dashboard-${vp.name}.png`);
  }
});

// Component-level visual testing
test('button variants', async ({ page }) => {
  await page.goto('/storybook/iframe.html?id=components-button--all-variants');
  await expect(page.locator('.story-container')).toHaveScreenshot('button-variants.png');
});
```

---

## Test Architecture

```typescript
// Test fixtures and factories

// Factory pattern (better than fixtures for complex objects)
import { faker } from '@faker-js/faker';

class UserFactory {
  static build(overrides: Partial<User> = {}): User {
    return {
      id: faker.string.uuid(),
      email: faker.internet.email(),
      name: faker.person.fullName(),
      role: 'user',
      createdAt: faker.date.past(),
      ...overrides,
    };
  }

  static buildList(count: number, overrides: Partial<User> = {}): User[] {
    return Array.from({ length: count }, () => this.build(overrides));
  }

  // For database tests (actually persists)
  static async create(overrides: Partial<User> = {}): Promise<User> {
    const user = this.build(overrides);
    return db.users.create({ data: user });
  }
}

class OrderFactory {
  static build(overrides: Partial<Order> = {}): Order {
    return {
      id: faker.string.uuid(),
      userId: faker.string.uuid(),
      status: 'pending',
      total: parseFloat(faker.commerce.price()),
      items: [OrderItemFactory.build()],
      createdAt: faker.date.recent(),
      ...overrides,
    };
  }
}

// Usage in tests
describe('OrderService', () => {
  it('calculates total correctly', () => {
    const order = OrderFactory.build({
      items: [
        OrderItemFactory.build({ price: 10, quantity: 2 }),
        OrderItemFactory.build({ price: 5, quantity: 3 }),
      ],
    });

    expect(calculateTotal(order)).toBe(35);
  });
});
```

### Test Doubles Guide

```typescript
// When to use which test double:

// STUB: Returns canned data (no verification)
const paymentGateway = {
  charge: vi.fn().mockResolvedValue({ success: true, transactionId: 'tx-123' }),
};

// MOCK: Verifies interactions (use sparingly)
const emailService = {
  send: vi.fn(),
};
// Later: expect(emailService.send).toHaveBeenCalledWith(expect.objectContaining({ to: 'user@test.com' }));

// SPY: Wraps real implementation, records calls
const spy = vi.spyOn(logger, 'error');
// Real logger.error still runs, but calls are recorded

// FAKE: Working implementation (simplified)
class FakeUserRepository implements UserRepository {
  private users: Map<string, User> = new Map();

  async findById(id: string): Promise<User | null> {
    return this.users.get(id) ?? null;
  }

  async save(user: User): Promise<void> {
    this.users.set(user.id, user);
  }
}

// Decision:
// Need to control return values? -> Stub
// Need to verify something was called? -> Mock (but prefer testing outcomes)
// Need real behavior + recording? -> Spy
// Need a working in-memory implementation? -> Fake
```

---

## Load Testing with k6

```javascript
// Soak test: sustained load over time (find memory leaks, connection exhaustion)
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '5m', target: 50 },    // Ramp up
    { duration: '4h', target: 50 },    // Sustained load
    { duration: '5m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(99)<1000'],
    http_req_failed: ['rate<0.01'],
  },
};

// Stress test: find breaking point
export const stressOptions = {
  stages: [
    { duration: '2m', target: 100 },
    { duration: '5m', target: 100 },
    { duration: '2m', target: 200 },
    { duration: '5m', target: 200 },
    { duration: '2m', target: 400 },
    { duration: '5m', target: 400 },
    { duration: '2m', target: 800 },   // Where does it break?
    { duration: '5m', target: 800 },
    { duration: '10m', target: 0 },    // Recovery
  ],
};

// Spike test: sudden traffic surge
export const spikeOptions = {
  stages: [
    { duration: '1m', target: 50 },    // Normal
    { duration: '10s', target: 1000 }, // Spike!
    { duration: '3m', target: 1000 },  // Sustained spike
    { duration: '10s', target: 50 },   // Back to normal
    { duration: '3m', target: 50 },    // Recovery
    { duration: '1m', target: 0 },
  ],
};
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| Testing implementation details | Tests break on refactor | Test behavior/outcomes, not internals |
| Excessive mocking | Tests pass but code is broken | Integration tests with real dependencies |
| No test isolation | Tests depend on execution order | Each test sets up and tears down its own state |
| Snapshot testing everything | Snapshots approved without review | Snapshots only for serializable output, review diffs |
| Flaky tests ignored | Erode trust in test suite | Fix or quarantine immediately |
| 100% coverage target | Tests for getters/setters, no real logic tested | Focus on mutation score for critical paths |
| No contract tests | Services break each other silently | Pact for service boundaries |
| Load testing only before launch | Performance degrades over time | Load tests in CI, fail on regression |

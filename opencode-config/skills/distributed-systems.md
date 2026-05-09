# Skill: Distributed Systems
# Loaded on-demand when task involves event-driven architecture, sagas, CQRS, message queues, idempotency, or service communication

## Auto-Detect

Trigger this skill when:
- Task mentions: event-driven, saga, CQRS, message queue, Kafka, RabbitMQ, idempotency
- Files: `docker-compose.yml` with queue services, `*.proto`, event handler files
- Patterns: service-to-service communication, eventual consistency, distributed transactions
- `package.json` contains: `kafkajs`, `amqplib`, `bullmq`, `@nestjs/microservices`, `temporal-sdk`

---

## Decision Tree: Communication Pattern

```
What's the interaction model?
├── Request-Response (synchronous)?
│   ├── Internal services, same team → gRPC (binary, streaming, codegen)
│   ├── External consumers → REST + OpenAPI
│   └── Need flexibility in queries → GraphQL
├── Fire-and-Forget (asynchronous)?
│   ├── At-least-once delivery required → Message Queue (Kafka, RabbitMQ)
│   ├── Exactly-once semantics needed → Kafka with idempotent producer + transactional consumer
│   └── Simple job dispatch → BullMQ / SQS
├── Event Notification (broadcast)?
│   ├── High throughput, ordered → Kafka (partitioned topics)
│   ├── Complex routing → RabbitMQ (exchanges + bindings)
│   └── Cloud-native → AWS EventBridge / Google Pub/Sub
└── Streaming (continuous data)?
    ├── Backpressure needed → gRPC streaming / Kafka Streams
    └── Real-time analytics → Apache Flink / Kafka Streams
```

## Decision Tree: Kafka vs RabbitMQ

```
├── Need event replay / audit log? → Kafka (log retention)
├── Need complex routing (topic, fanout, headers)? → RabbitMQ
├── Need strict ordering per partition? → Kafka
├── Need priority queues? → RabbitMQ
├── Throughput > 100k msg/sec? → Kafka
├── Need dead-letter + retry with backoff? → RabbitMQ (native DLX)
└── Need both pub/sub AND work queues? → RabbitMQ (exchanges)
```

---

## CQRS Pattern

```typescript
// Command side — writes
interface Command {
  type: string;
  payload: unknown;
  metadata: { correlationId: string; causationId: string; timestamp: Date };
}

class OrderCommandHandler {
  constructor(
    private readonly eventStore: EventStore,
    private readonly eventBus: EventBus
  ) {}

  async handle(cmd: CreateOrderCommand): Promise<void> {
    // Validate business rules
    const order = Order.create(cmd.payload);

    // Persist events (not state)
    const events = order.getUncommittedEvents();
    await this.eventStore.append(order.id, events);

    // Publish for projections
    await this.eventBus.publishAll(events);
  }
}

// Query side — reads (separate database, optimized for reads)
class OrderQueryService {
  constructor(private readonly readDb: ReadDatabase) {}

  async getOrderSummary(orderId: string): Promise<OrderSummaryDTO> {
    // Read from denormalized projection
    return this.readDb.query('SELECT * FROM order_summaries WHERE id = $1', [orderId]);
  }
}

// Projection — event handler that builds read models
class OrderProjection {
  @EventHandler(OrderCreatedEvent)
  async onOrderCreated(event: OrderCreatedEvent): Promise<void> {
    await this.readDb.upsert('order_summaries', {
      id: event.aggregateId,
      status: 'created',
      total: event.payload.total,
      createdAt: event.timestamp,
    });
  }
}
```

---

## Saga Pattern (Orchestration)

```typescript
// Orchestrator-based saga for distributed transactions
class OrderSaga {
  private steps: SagaStep[] = [
    {
      execute: (ctx) => this.paymentService.charge(ctx.orderId, ctx.amount),
      compensate: (ctx) => this.paymentService.refund(ctx.orderId, ctx.amount),
    },
    {
      execute: (ctx) => this.inventoryService.reserve(ctx.orderId, ctx.items),
      compensate: (ctx) => this.inventoryService.release(ctx.orderId, ctx.items),
    },
    {
      execute: (ctx) => this.shippingService.schedule(ctx.orderId, ctx.address),
      compensate: (ctx) => this.shippingService.cancel(ctx.orderId),
    },
  ];

  async execute(context: OrderContext): Promise<SagaResult> {
    const completedSteps: number[] = [];

    for (let i = 0; i < this.steps.length; i++) {
      try {
        await this.steps[i].execute(context);
        completedSteps.push(i);
      } catch (error) {
        // Compensate in reverse order
        for (const stepIndex of completedSteps.reverse()) {
          try {
            await this.steps[stepIndex].compensate(context);
          } catch (compensateError) {
            // Log and alert — manual intervention needed
            await this.alertOps(context, stepIndex, compensateError);
          }
        }
        return { success: false, failedAt: i, error };
      }
    }
    return { success: true };
  }
}
```

---

## Idempotency

```typescript
// Idempotency key middleware
class IdempotencyMiddleware {
  constructor(private readonly store: IdempotencyStore) {}

  async handle(req: Request, next: () => Promise<Response>): Promise<Response> {
    const key = req.headers['idempotency-key'];
    if (!key) return next(); // Non-idempotent request

    // Check if already processed
    const cached = await this.store.get(key);
    if (cached) {
      if (cached.status === 'processing') {
        return new Response(null, { status: 409 }); // Conflict — in progress
      }
      return cached.response; // Return cached response
    }

    // Mark as processing (with TTL)
    await this.store.set(key, { status: 'processing' }, { ttl: 300 });

    try {
      const response = await next();
      await this.store.set(key, { status: 'complete', response }, { ttl: 86400 });
      return response;
    } catch (error) {
      await this.store.delete(key); // Allow retry on failure
      throw error;
    }
  }
}

// Database-level idempotency with unique constraints
// INSERT INTO processed_events (event_id, result) VALUES ($1, $2)
// ON CONFLICT (event_id) DO NOTHING;
```

---

## Circuit Breaker

```typescript
enum CircuitState { CLOSED, OPEN, HALF_OPEN }

class CircuitBreaker {
  private state = CircuitState.CLOSED;
  private failures = 0;
  private lastFailure: number = 0;
  private successesInHalfOpen = 0;

  constructor(
    private readonly options: {
      failureThreshold: number;    // e.g., 5
      recoveryTimeout: number;     // e.g., 30000ms
      halfOpenRequests: number;    // e.g., 3
    }
  ) {}

  async call<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === CircuitState.OPEN) {
      if (Date.now() - this.lastFailure > this.options.recoveryTimeout) {
        this.state = CircuitState.HALF_OPEN;
        this.successesInHalfOpen = 0;
      } else {
        throw new CircuitOpenError('Circuit is open');
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private onSuccess(): void {
    if (this.state === CircuitState.HALF_OPEN) {
      this.successesInHalfOpen++;
      if (this.successesInHalfOpen >= this.options.halfOpenRequests) {
        this.state = CircuitState.CLOSED;
        this.failures = 0;
      }
    } else {
      this.failures = 0;
    }
  }

  private onFailure(): void {
    this.failures++;
    this.lastFailure = Date.now();
    if (this.failures >= this.options.failureThreshold) {
      this.state = CircuitState.OPEN;
    }
  }
}
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| Distributed monolith | Services tightly coupled via sync calls | Use async events, accept eventual consistency |
| Two-phase commit across services | Blocks resources, doesn't scale | Use saga pattern with compensating transactions |
| Shared database between services | Coupling, schema conflicts | Each service owns its data, sync via events |
| No idempotency on consumers | Duplicate processing on retry | Idempotency keys + deduplication table |
| Unbounded retries | Cascading failures, resource exhaustion | Exponential backoff + circuit breaker + DLQ |
| Event ordering assumptions | Race conditions across partitions | Use partition keys, or design for out-of-order |
| Fat events with full entity | Coupling, bandwidth waste | Thin events + query back for details if needed |
| Sync calls in event handlers | Blocks consumer, creates coupling | Keep handlers fast, offload to separate workers |

---

## Eventual Consistency Strategies

```typescript
// Strategy 1: Polling with version check
async function syncWithRetry(entityId: string, expectedVersion: number): Promise<Entity> {
  for (let attempt = 0; attempt < 5; attempt++) {
    const entity = await queryService.get(entityId);
    if (entity.version >= expectedVersion) return entity;
    await sleep(100 * Math.pow(2, attempt)); // Exponential backoff
  }
  throw new ConsistencyTimeoutError(entityId, expectedVersion);
}

// Strategy 2: Read-your-writes via sticky sessions
// Route user to same read replica after write

// Strategy 3: Causal consistency with vector clocks
interface VectorClock {
  [nodeId: string]: number;
}

function happensBefore(a: VectorClock, b: VectorClock): boolean {
  return Object.keys(a).every(key => (a[key] ?? 0) <= (b[key] ?? 0)) &&
    Object.keys(a).some(key => (a[key] ?? 0) < (b[key] ?? 0));
}
```

---

## Message Queue Best Practices

1. **Always set TTL** on messages — prevent queue buildup from dead consumers
2. **Use dead-letter queues** — capture failed messages for investigation
3. **Partition by aggregate ID** — ensures ordering within an entity
4. **Consumer groups** — scale horizontally while maintaining partition assignment
5. **Schema registry** — version your event schemas (Avro/Protobuf)
6. **Backpressure** — consumer should control pull rate, not producer push rate
7. **Poison pill handling** — detect and quarantine messages that always fail
8. **Correlation IDs** — thread through all messages for distributed tracing

```typescript
// Producer with proper metadata
await producer.send({
  topic: 'order.events',
  messages: [{
    key: order.id, // Partition key — ensures ordering per order
    value: JSON.stringify(event),
    headers: {
      'correlation-id': correlationId,
      'causation-id': causationId,
      'event-type': 'OrderCreated',
      'schema-version': '2',
      'produced-at': new Date().toISOString(),
    },
  }],
});
```

---

## Service Mesh Considerations

```
When to add a service mesh (Istio/Linkerd):
├── > 10 services communicating? → Yes, mesh handles mTLS + observability
├── Need canary deployments with traffic splitting? → Yes
├── Need per-request retry/timeout policies? → Yes (vs. coding in each service)
├── < 5 services, simple topology? → No, overhead not worth it
└── Team < 5 engineers? → No, operational complexity too high
```

Key mesh features to leverage:
- **mTLS everywhere** — zero-trust between services without app code changes
- **Traffic policies** — retries, timeouts, circuit breaking at infrastructure level
- **Observability** — automatic distributed tracing without SDK instrumentation
- **Traffic splitting** — canary releases, A/B testing at network level

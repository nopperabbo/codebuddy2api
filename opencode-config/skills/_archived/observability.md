# Skill: Observability
# Loaded on-demand when task involves monitoring, logging, tracing, metrics, alerting, or SLO/SLI

## Auto-Detect

Trigger this skill when:
- Task mentions: monitoring, logging, tracing, metrics, Prometheus, Grafana, OpenTelemetry
- Files: `otel-config.yaml`, `prometheus.yml`, `grafana/`, `*.dashboard.json`
- Patterns: structured logging, distributed tracing, alerting, SLO definition
- `package.json` contains: `@opentelemetry/*`, `prom-client`, `winston`, `pino`

---

## Three Pillars Decision Tree

```
What do you need to understand?
├── What happened? (discrete events)
│   └── LOGS — structured, contextual, searchable
├── How much / how fast? (aggregated measurements)
│   └── METRICS — counters, gauges, histograms
├── Where did time go? (request flow across services)
│   └── TRACES — spans with parent-child relationships
└── All three together?
    └── OpenTelemetry (unified SDK, correlate via trace_id)
```

---

## OpenTelemetry Setup (TypeScript)

```typescript
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { Resource } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';

const sdk = new NodeSDK({
  resource: new Resource({
    [ATTR_SERVICE_NAME]: 'order-service',
    [ATTR_SERVICE_VERSION]: '1.4.2',
    'deployment.environment': process.env.NODE_ENV,
  }),
  traceExporter: new OTLPTraceExporter({
    url: 'http://otel-collector:4318/v1/traces',
  }),
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter({
      url: 'http://otel-collector:4318/v1/metrics',
    }),
    exportIntervalMillis: 15000,
  }),
  instrumentations: [
    getNodeAutoInstrumentations({
      '@opentelemetry/instrumentation-fs': { enabled: false }, // Too noisy
    }),
  ],
});

sdk.start();
process.on('SIGTERM', () => sdk.shutdown());
```

---

## Structured Logging

```typescript
import pino from 'pino';

// Base logger with service context
const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  formatters: {
    level: (label) => ({ level: label }), // Use string labels, not numbers
  },
  base: {
    service: 'order-service',
    version: '1.4.2',
    environment: process.env.NODE_ENV,
  },
  redact: ['req.headers.authorization', 'body.password', 'body.creditCard'],
  timestamp: pino.stdTimeFunctions.isoTime,
});

// Request-scoped logger with trace context
function createRequestLogger(req: Request): pino.Logger {
  return logger.child({
    requestId: req.headers['x-request-id'],
    traceId: req.headers['traceparent']?.split('-')[1],
    userId: req.user?.id,
    method: req.method,
    path: req.url,
  });
}

// Usage — structured, not string interpolation
log.info({ orderId, itemCount: items.length, total }, 'Order created');
log.error({ err, orderId, retryCount }, 'Payment processing failed');

// NEVER do this:
// log.info(`Order ${orderId} created with ${items.length} items`); // Unsearchable
```

### Log Levels Guide

| Level | Use For | Example |
|-------|---------|---------|
| `fatal` | App cannot continue | Database connection pool exhausted |
| `error` | Operation failed, needs attention | Payment gateway timeout after retries |
| `warn` | Degraded but functional | Cache miss rate > 50%, using fallback |
| `info` | Business events, state changes | Order created, user signed up |
| `debug` | Diagnostic detail | SQL query executed, cache hit/miss |
| `trace` | Very verbose, development only | Function entry/exit, variable values |

---

## Metrics with Prometheus

```typescript
import { Counter, Histogram, Gauge, Registry } from 'prom-client';

const registry = new Registry();

// RED metrics (Rate, Errors, Duration) — for every service
const httpRequestsTotal = new Counter({
  name: 'http_requests_total',
  help: 'Total HTTP requests',
  labelNames: ['method', 'path', 'status_code'] as const,
  registers: [registry],
});

const httpRequestDuration = new Histogram({
  name: 'http_request_duration_seconds',
  help: 'HTTP request duration in seconds',
  labelNames: ['method', 'path', 'status_code'] as const,
  buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
  registers: [registry],
});

// USE metrics (Utilization, Saturation, Errors) — for resources
const dbPoolUtilization = new Gauge({
  name: 'db_pool_utilization_ratio',
  help: 'Database connection pool utilization (0-1)',
  registers: [registry],
});

const queueDepth = new Gauge({
  name: 'queue_depth',
  help: 'Number of messages waiting in queue',
  labelNames: ['queue_name'] as const,
  registers: [registry],
});

// Business metrics
const ordersCreated = new Counter({
  name: 'orders_created_total',
  help: 'Total orders created',
  labelNames: ['payment_method', 'region'] as const,
  registers: [registry],
});

// Middleware to record metrics
function metricsMiddleware(req: Request, res: Response, next: NextFunction) {
  const end = httpRequestDuration.startTimer();
  res.on('finish', () => {
    const labels = { method: req.method, path: req.route?.path || 'unknown', status_code: res.statusCode };
    httpRequestsTotal.inc(labels);
    end(labels);
  });
  next();
}
```

---

## SLO/SLI/SLA Framework

```
SLA (Agreement) → What you promise to customers (contractual)
SLO (Objective) → Internal target, stricter than SLA (operational)
SLI (Indicator) → The actual measurement (technical)

Example:
  SLA: 99.9% availability (contractual, with penalties)
  SLO: 99.95% availability (internal target, gives buffer)
  SLI: (successful requests / total requests) over 30-day window
```

### Defining SLOs

```yaml
# slo.yaml — machine-readable SLO definitions
slos:
  - name: order-api-availability
    description: "Order API returns successful responses"
    sli:
      type: availability
      good_events: "http_requests_total{status_code!~'5..'}"
      total_events: "http_requests_total"
    objective: 99.95
    window: 30d
    error_budget: 0.05  # 21.6 minutes/month

  - name: order-api-latency
    description: "Order API responds within acceptable time"
    sli:
      type: latency
      threshold: 500ms
      good_events: "http_request_duration_seconds_bucket{le='0.5'}"
      total_events: "http_requests_total"
    objective: 99.0
    window: 30d

  - name: payment-processing
    description: "Payments complete successfully"
    sli:
      type: quality
      good_events: "payments_total{status='success'}"
      total_events: "payments_total"
    objective: 99.9
    window: 7d
```

### Error Budget Calculation

```typescript
interface ErrorBudget {
  sloTarget: number;          // e.g., 99.95
  windowDays: number;         // e.g., 30
  totalRequests: number;      // in window
  failedRequests: number;     // in window
  budgetTotal: number;        // allowed failures
  budgetRemaining: number;    // failures left before breach
  budgetConsumedPercent: number;
  burnRate: number;           // current consumption rate
}

function calculateErrorBudget(slo: SLO, metrics: WindowMetrics): ErrorBudget {
  const budgetTotal = metrics.totalRequests * (1 - slo.objective / 100);
  const budgetRemaining = budgetTotal - metrics.failedRequests;
  const budgetConsumedPercent = (metrics.failedRequests / budgetTotal) * 100;
  const elapsedRatio = metrics.elapsedDays / slo.windowDays;
  const burnRate = budgetConsumedPercent / (elapsedRatio * 100);

  return { ...slo, ...metrics, budgetTotal, budgetRemaining, budgetConsumedPercent, burnRate };
}
```

---

## Alerting Strategy

### Multi-Window Burn Rate Alerts (Google SRE approach)

```yaml
# Prometheus alerting rules
groups:
  - name: slo-burn-rate
    rules:
      # Page: 2% budget consumed in 1 hour (14.4x burn rate)
      - alert: HighErrorBurnRate_Page
        expr: |
          (
            sum(rate(http_requests_total{status_code=~"5.."}[1h]))
            / sum(rate(http_requests_total[1h]))
          ) > (14.4 * 0.0005)
          AND
          (
            sum(rate(http_requests_total{status_code=~"5.."}[5m]))
            / sum(rate(http_requests_total[5m]))
          ) > (14.4 * 0.0005)
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "High error burn rate — will exhaust budget in 2.5 days"

      # Ticket: 5% budget consumed in 6 hours (2x burn rate)
      - alert: HighErrorBurnRate_Ticket
        expr: |
          (
            sum(rate(http_requests_total{status_code=~"5.."}[6h]))
            / sum(rate(http_requests_total[6h]))
          ) > (2 * 0.0005)
        for: 30m
        labels:
          severity: ticket
        annotations:
          summary: "Elevated error rate — investigate within business hours"
```

### Alert Quality Checklist

- [ ] Does this alert require human action? (If not, don't alert)
- [ ] Is the alert actionable? (Runbook linked?)
- [ ] Does it fire before customers notice? (Leading indicator)
- [ ] Is it based on symptoms, not causes? (Alert on error rate, not CPU)
- [ ] Does it have appropriate severity? (Page vs ticket vs log)
- [ ] Is there a clear owner? (Routing to correct team)

---

## Distributed Tracing Best Practices

```typescript
import { trace, SpanKind, SpanStatusCode } from '@opentelemetry/api';

const tracer = trace.getTracer('order-service');

async function processOrder(order: Order): Promise<void> {
  // Create a span for the operation
  return tracer.startActiveSpan('processOrder', {
    kind: SpanKind.INTERNAL,
    attributes: {
      'order.id': order.id,
      'order.item_count': order.items.length,
      'order.total': order.total,
    },
  }, async (span) => {
    try {
      // Child span for payment
      await tracer.startActiveSpan('chargePayment', {
        kind: SpanKind.CLIENT,
        attributes: { 'payment.method': order.paymentMethod },
      }, async (paymentSpan) => {
        await paymentService.charge(order);
        paymentSpan.setStatus({ code: SpanStatusCode.OK });
        paymentSpan.end();
      });

      // Add event (point-in-time annotation)
      span.addEvent('payment_completed', { 'payment.transaction_id': txId });

      span.setStatus({ code: SpanStatusCode.OK });
    } catch (error) {
      span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
      span.recordException(error);
      throw error;
    } finally {
      span.end();
    }
  });
}
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| Logging PII/secrets | Compliance violation, security risk | Redact at logger level, use allowlists |
| High-cardinality labels | Prometheus OOM, slow queries | Never use userId/requestId as metric label |
| Alert on every error | Alert fatigue, ignored pages | Alert on SLO burn rate, not individual errors |
| No correlation between pillars | Can't connect log → trace → metric | Use trace_id in logs, exemplars in metrics |
| Sampling at 100% in production | Storage costs explode | Head-based sampling 1-10%, tail-based for errors |
| Dashboard without runbook | Alert fires, nobody knows what to do | Every alert links to a runbook |
| Monitoring only happy path | Blind to degradation | Monitor error paths, timeouts, retries |
| String-based log parsing | Fragile, slow, breaks on format change | Structured JSON logging from day one |

---

## Runbook Template

```markdown
## Alert: [Alert Name]

### What it means
[One sentence explaining the symptom]

### Impact
[What users experience when this fires]

### Investigation Steps
1. Check [dashboard link] for the affected service
2. Look at recent deployments: `kubectl rollout history deployment/X`
3. Check dependent services: [list]
4. Review logs: `query: {service="X", level="error"} | json`

### Mitigation
- [ ] If caused by deployment → rollback: `kubectl rollout undo deployment/X`
- [ ] If caused by traffic spike → scale: `kubectl scale deployment/X --replicas=N`
- [ ] If caused by dependency → enable circuit breaker / failover

### Escalation
- Primary: @team-channel
- Secondary (after 15min): @oncall-lead
- P1 (data loss risk): @engineering-director
```

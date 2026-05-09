# Skill: Reliability Engineering
# Loaded on-demand when task involves chaos engineering, error budgets, capacity planning, incident response, or load testing

## Auto-Detect

Trigger this skill when:
- Task mentions: SRE, reliability, chaos engineering, load testing, incident, postmortem
- Files: `k6/`, `locust/`, `*.jmx`, `chaos-*.yaml`, `incident-*.md`
- Patterns: error budget, capacity planning, failover, disaster recovery
- `package.json` contains: `k6`, `artillery`, `@chaos-mesh/*`

---

## Decision Tree: Reliability Investment

```
What's your reliability maturity?
├── Level 0: No monitoring, manual deploys
│   └── Priority: Add basic health checks + structured logging + CI/CD
├── Level 1: Basic monitoring, some alerts
│   └── Priority: Define SLOs, add distributed tracing, automate rollbacks
├── Level 2: SLOs defined, automated deploys
│   └── Priority: Error budgets, load testing, incident process
├── Level 3: Error budget-driven, regular load tests
│   └── Priority: Chaos engineering, capacity planning, game days
└── Level 4: Proactive reliability
    └── Priority: Predictive scaling, automated remediation, continuous verification
```

---

## Error Budget Policy

```typescript
interface ErrorBudgetPolicy {
  // When budget is healthy (> 50% remaining)
  healthy: {
    deployFrequency: 'unlimited';
    experimentationAllowed: true;
    featureFlagRolloutSpeed: 'aggressive'; // 25% → 50% → 100% in hours
  };
  // When budget is concerning (25-50% remaining)
  caution: {
    deployFrequency: 'normal';
    experimentationAllowed: true;
    featureFlagRolloutSpeed: 'moderate'; // 5% → 25% → 50% → 100% over days
  };
  // When budget is low (< 25% remaining)
  critical: {
    deployFrequency: 'reduced'; // Only bug fixes and reliability improvements
    experimentationAllowed: false;
    featureFlagRolloutSpeed: 'conservative'; // 1% → 5% → 25% over week
  };
  // When budget is exhausted (0% remaining)
  frozen: {
    deployFrequency: 'emergency-only'; // Reliability fixes only
    experimentationAllowed: false;
    mandatoryActions: [
      'All hands on reliability improvements',
      'Postmortem for budget exhaustion',
      'Architecture review for systemic issues',
    ];
  };
}
```

---

## Chaos Engineering

### Principles

1. **Start with a hypothesis** — "If X fails, the system should Y"
2. **Minimize blast radius** — Start in staging, then canary in prod
3. **Automate rollback** — Abort experiment if impact exceeds threshold
4. **Run in production** — Staging doesn't reflect real conditions
5. **Make it continuous** — Not a one-time exercise

### Experiment Design

```typescript
interface ChaosExperiment {
  name: string;
  hypothesis: string;
  steadyState: {
    metric: string;
    threshold: number;
    window: string;
  };
  injection: {
    type: 'latency' | 'failure' | 'resource' | 'network' | 'state';
    target: string;
    parameters: Record<string, unknown>;
    duration: string;
  };
  abort: {
    condition: string; // e.g., "error_rate > 5% for 1m"
    action: 'rollback' | 'halt';
  };
  schedule: 'manual' | 'weekly' | 'continuous';
}

// Example: Database failover test
const dbFailoverExperiment: ChaosExperiment = {
  name: 'primary-db-failover',
  hypothesis: 'When primary DB fails, system fails over to replica within 30s with < 1% error rate',
  steadyState: {
    metric: 'http_requests_total{status_code=~"5.."}',
    threshold: 0.001, // 0.1% error rate
    window: '5m',
  },
  injection: {
    type: 'network',
    target: 'postgres-primary',
    parameters: { action: 'partition', duration: '60s' },
    duration: '60s',
  },
  abort: {
    condition: 'error_rate > 5% for 30s',
    action: 'rollback',
  },
  schedule: 'weekly',
};
```

### Common Chaos Scenarios

```yaml
# Kubernetes chaos with Chaos Mesh
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: payment-service-latency
spec:
  action: delay
  mode: all
  selector:
    namespaces: [production]
    labelSelectors:
      app: payment-service
  delay:
    latency: "500ms"
    jitter: "100ms"
    correlation: "50"
  duration: "5m"
  scheduler:
    cron: "@weekly"
---
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: random-pod-kill
spec:
  action: pod-kill
  mode: one
  selector:
    namespaces: [production]
    labelSelectors:
      tier: backend
  scheduler:
    cron: "0 10 * * 1-5"  # Weekdays at 10am
```

---

## Load Testing with k6

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const orderLatency = new Trend('order_creation_latency');

// Load profile: ramp up → steady → spike → cool down
export const options = {
  stages: [
    { duration: '2m', target: 100 },   // Ramp up
    { duration: '5m', target: 100 },   // Steady state
    { duration: '30s', target: 500 },  // Spike
    { duration: '2m', target: 500 },   // Sustained spike
    { duration: '1m', target: 100 },   // Recovery
    { duration: '2m', target: 0 },     // Cool down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],  // Latency SLO
    errors: ['rate<0.01'],                            // Error rate SLO
    order_creation_latency: ['p(95)<800'],            // Business SLO
  },
};

export default function () {
  // Simulate realistic user journey
  const loginRes = http.post(`${__ENV.BASE_URL}/api/auth/login`, JSON.stringify({
    email: `user${__VU}@test.com`,
    password: 'testpass',
  }), { headers: { 'Content-Type': 'application/json' } });

  check(loginRes, { 'login successful': (r) => r.status === 200 });
  const token = loginRes.json('token');

  sleep(Math.random() * 2); // Think time

  // Create order
  const start = Date.now();
  const orderRes = http.post(`${__ENV.BASE_URL}/api/orders`, JSON.stringify({
    items: [{ productId: 'prod-1', quantity: 2 }],
  }), {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  });

  orderLatency.add(Date.now() - start);
  errorRate.add(orderRes.status >= 400);

  check(orderRes, {
    'order created': (r) => r.status === 201,
    'has order id': (r) => r.json('id') !== undefined,
  });

  sleep(1 + Math.random() * 3);
}
```

---

## Capacity Planning

```typescript
// Capacity model
interface CapacityModel {
  current: {
    peakRPS: number;           // Current peak requests/sec
    avgLatencyMs: number;      // At peak
    cpuUtilization: number;    // At peak (0-1)
    memoryUtilization: number; // At peak (0-1)
    instances: number;
  };
  growth: {
    monthlyTrafficGrowthPercent: number;
    seasonalMultiplier: number;  // e.g., 3x for Black Friday
  };
  targets: {
    maxCpuUtilization: number;  // e.g., 0.7 (headroom for spikes)
    maxLatencyMs: number;
    minAvailability: number;
  };
}

function planCapacity(model: CapacityModel, monthsAhead: number): CapacityPlan {
  const projectedRPS = model.current.peakRPS *
    Math.pow(1 + model.growth.monthlyTrafficGrowthPercent / 100, monthsAhead) *
    model.growth.seasonalMultiplier;

  const rpsPerInstance = model.current.peakRPS / model.current.instances;
  const targetRpsPerInstance = rpsPerInstance * (model.targets.maxCpuUtilization / model.current.cpuUtilization);

  const requiredInstances = Math.ceil(projectedRPS / targetRpsPerInstance);
  const withRedundancy = Math.ceil(requiredInstances * 1.5); // N+1 or 50% headroom

  return {
    projectedRPS,
    requiredInstances,
    withRedundancy,
    scaleDate: calculateScaleDate(model),
    recommendations: generateRecommendations(model, requiredInstances),
  };
}
```

---

## Incident Response

### Severity Levels

| Level | Criteria | Response Time | Example |
|-------|----------|---------------|---------|
| SEV1 | Data loss, full outage, security breach | 5 min | Database corruption, auth bypass |
| SEV2 | Major feature broken, significant degradation | 15 min | Payments failing, 50% error rate |
| SEV3 | Minor feature broken, workaround exists | 1 hour | Search slow, export failing |
| SEV4 | Cosmetic, no user impact | Next business day | Dashboard typo, log noise |

### Incident Commander Checklist

```markdown
## Incident Response Checklist

### Triage (first 5 minutes)
- [ ] Acknowledge alert, claim incident commander role
- [ ] Assess severity level
- [ ] Create incident channel (#inc-YYYY-MM-DD-brief-description)
- [ ] Page relevant team if SEV1/SEV2
- [ ] Post initial status: what we know, what we don't

### Mitigate (next 15-60 minutes)
- [ ] Identify blast radius (which users/regions affected?)
- [ ] Attempt quick mitigation (rollback, feature flag, scale)
- [ ] If rollback works → monitor for 15 min → declare mitigated
- [ ] If not → escalate, bring in subject matter experts
- [ ] Update status page every 15 minutes

### Resolve
- [ ] Root cause identified
- [ ] Fix deployed and verified
- [ ] Monitoring confirms recovery
- [ ] Affected users notified
- [ ] Incident declared resolved

### Follow-up (within 48 hours)
- [ ] Write postmortem (blameless)
- [ ] Identify action items
- [ ] Schedule postmortem review meeting
- [ ] Update runbooks if needed
```

---

## Postmortem Template

```markdown
## Postmortem: [Incident Title]
**Date:** YYYY-MM-DD | **Duration:** X hours | **Severity:** SEV-N
**Author:** [Name] | **Reviewers:** [Names]

### Summary
[2-3 sentences: what happened, impact, resolution]

### Impact
- Users affected: [number/percentage]
- Revenue impact: [if applicable]
- SLO budget consumed: [X% of monthly budget]

### Timeline (UTC)
| Time | Event |
|------|-------|
| 14:00 | Deploy v2.3.1 rolled out |
| 14:05 | Error rate spike detected by monitoring |
| 14:08 | Alert fired, IC acknowledged |
| 14:15 | Root cause identified: missing DB index |
| 14:20 | Rollback initiated |
| 14:25 | Service recovered |

### Root Cause
[Technical explanation of what went wrong]

### Contributing Factors
- [Factor 1: e.g., no load test for new query pattern]
- [Factor 2: e.g., missing index not caught in review]

### What Went Well
- [e.g., Alert fired within 5 minutes]
- [e.g., Rollback was fast and clean]

### What Went Poorly
- [e.g., No runbook for this scenario]
- [e.g., Took 10 min to identify which deploy caused it]

### Action Items
| Action | Owner | Priority | Due Date |
|--------|-------|----------|----------|
| Add load test for search queries | @alice | P1 | 2024-02-01 |
| Add DB migration review checklist | @bob | P2 | 2024-02-15 |
| Improve deploy correlation in dashboards | @carol | P2 | 2024-02-15 |

### Lessons Learned
[Key takeaways for the broader organization]
```

---

## Failover Strategies

```
Active-Passive:
├── Primary handles all traffic
├── Secondary on standby (warm/hot)
├── Failover on primary failure (manual or automatic)
└── Use when: cost-sensitive, can tolerate brief downtime

Active-Active:
├── Both handle traffic simultaneously
├── Load balanced across regions/zones
├── No failover needed — traffic shifts automatically
└── Use when: zero-downtime required, global users

Pilot Light:
├── Minimal infrastructure always running (DB replicas)
├── Scale up compute on failover
├── Recovery time: 10-30 minutes
└── Use when: DR required but cost must be low

Multi-Region Active:
├── Full stack in multiple regions
├── Data replicated (async or sync)
├── DNS/load balancer routes to nearest healthy region
└── Use when: global SLA, regulatory requirements
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| Testing only happy path | Failures in production surprise you | Chaos engineering, fault injection in CI |
| No error budget policy | Teams argue about reliability vs features | Define policy: what happens at each budget level |
| Heroic incident response | Burnout, knowledge silos | Runbooks, rotation, blameless culture |
| Load testing in staging only | Staging ≠ production (data, traffic patterns) | Shadow traffic, canary load tests in prod |
| Single point of failure | One component takes everything down | Redundancy at every layer, blast radius limits |
| Manual scaling | Can't respond to traffic spikes fast enough | Auto-scaling with proper metrics (not just CPU) |
| Postmortem blame | People hide mistakes, no learning | Blameless postmortems, focus on systems |
| Over-engineering reliability | 99.999% when 99.9% is sufficient | Match reliability to business requirements |

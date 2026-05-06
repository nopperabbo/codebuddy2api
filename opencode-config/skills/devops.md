# Skill: DevOps Advanced
# Loaded on-demand when task involves Docker, CI/CD, deployment, monitoring, or infrastructure

## Auto-Detect

Trigger this skill when:
- Files: `Dockerfile`, `docker-compose.yml`, `.github/workflows/*.yml`, `Jenkinsfile`
- Files: `.gitlab-ci.yml`, `fly.toml`, `railway.json`, `vercel.json`, `terraform/*.tf`
- Task mentions: deploy, container, pipeline, monitoring, infrastructure, scaling
- `package.json` scripts: `docker:*`, `deploy:*`, `ci:*`

---

## Decision Tree: Deployment Strategy

```
What's your risk tolerance and infrastructure?
├── Zero-downtime required, instant rollback needed?
│   └── Blue-Green deployment
│       ├── Two identical environments (blue = current, green = new)
│       ├── Deploy to green, test, switch traffic
│       └── Rollback = switch back to blue (instant)
├── Gradual rollout, want to test with real traffic?
│   └── Canary deployment
│       ├── Route 1-5% traffic to new version
│       ├── Monitor error rates, latency, business metrics
│       ├── Gradually increase (10% → 25% → 50% → 100%)
│       └── Rollback = route all traffic back to old version
├── Simple app, can tolerate brief mixed versions?
│   └── Rolling deployment (Kubernetes default)
│       ├── Replace instances one at a time
│       ├── Old and new versions run simultaneously during rollout
│       └── Rollback = roll forward or `kubectl rollout undo`
├── Feature needs testing with specific users?
│   └── Feature flags (LaunchDarkly, Unleash, custom)
│       ├── Deploy code dark (disabled)
│       ├── Enable per-user, per-team, per-percentage
│       └── Rollback = disable flag (instant, no deploy)
└── Database migration involved?
    └── Expand-Contract pattern
        ├── Phase 1: Add new column/table (expand) — backward compatible
        ├── Phase 2: Migrate data, update code to use new schema
        └── Phase 3: Remove old column/table (contract) — after all instances updated
```

## Decision Tree: Container Orchestration

```
How many containers/services?
├── 1-3 services, single server?
│   └── Docker Compose (simplest, good enough for most)
├── Need auto-scaling, self-healing, multi-node?
│   └── Kubernetes (EKS/GKE/AKS or k3s for lightweight)
├── Serverless containers (no cluster management)?
│   └── AWS Fargate / Google Cloud Run / Azure Container Apps
├── Simple PaaS (just deploy and forget)?
│   └── Railway / Fly.io / Render
└── Static site + API?
    └── Vercel / Netlify (frontend) + serverless functions or separate API
```

---

## Docker Best Practices

### Optimized Dockerfile
```dockerfile
# Stage 1: Dependencies (cached unless package files change)
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --only=production && \
    cp -R node_modules /prod_modules && \
    npm ci

# Stage 2: Build
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build && \
    npm prune --production

# Stage 3: Production (minimal image)
FROM node:22-alpine AS runtime
RUN addgroup -S app && adduser -S app -G app
WORKDIR /app

# Copy only what's needed
COPY --from=builder --chown=app:app /app/dist ./dist
COPY --from=builder --chown=app:app /app/node_modules ./node_modules
COPY --from=builder --chown=app:app /app/package.json ./

USER app
ENV NODE_ENV=production
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/health || exit 1

CMD ["node", "dist/index.js"]
```

### Docker Checklist
- [ ] Multi-stage build (separate build/runtime)
- [ ] Non-root user (`USER app`)
- [ ] `.dockerignore` excludes: `node_modules`, `.git`, `.env`, `*.md`, `tests/`
- [ ] Pin base image version (or digest for reproducibility)
- [ ] HEALTHCHECK defined
- [ ] No secrets in image (use runtime env vars or Docker secrets)
- [ ] One process per container
- [ ] Minimal base image (Alpine or distroless)
- [ ] Layer ordering optimized (deps before source)
- [ ] `npm ci` not `npm install` (deterministic)

### Docker Compose (Development)
```yaml
services:
  app:
    build: .
    ports: ["3000:3000"]
    environment:
      - DATABASE_URL=postgres://user:pass@db:5432/app
      - REDIS_URL=redis://cache:6379
    depends_on:
      db: { condition: service_healthy }
      cache: { condition: service_started }
    volumes:
      - ./src:/app/src  # Hot reload in dev
    develop:
      watch:
        - action: sync
          path: ./src
          target: /app/src

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d app"]
      interval: 5s
      timeout: 3s
      retries: 5

  cache:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

volumes:
  pgdata:
```

---

## CI/CD Pipeline Patterns

### GitHub Actions Template
```yaml
name: CI/CD
on:
  push: { branches: [main] }
  pull_request: { branches: [main] }

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm }
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run test -- --coverage
      - run: npm audit --audit-level=moderate

  build:
    needs: quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{ github.ref == 'refs/heads/main' }}
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    if: github.ref == 'refs/heads/main'
    needs: build
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: echo "Deploy image ghcr.io/${{ github.repository }}:${{ github.sha }}"
      # Add your deployment step (kubectl, fly deploy, railway, etc.)
```

### Pipeline Principles
- **Every push**: lint → typecheck → test → security scan → build
- **PR only**: preview deploy, visual regression tests
- **Main only**: build image → deploy staging → smoke test → deploy production
- **Concurrency**: cancel in-progress runs for same branch
- **Caching**: npm cache, Docker layer cache, test result cache
- **Secrets**: GitHub Secrets / environment-scoped, never in code

---

## Monitoring Checklist

### The Four Golden Signals
| Signal | What to Measure | Alert When |
|--------|----------------|------------|
| **Latency** | p50, p95, p99 response time | p95 > 500ms for 5 min |
| **Traffic** | Requests/sec, concurrent users | Unusual spike or drop |
| **Errors** | 5xx rate, error ratio | Error rate > 1% for 2 min |
| **Saturation** | CPU, memory, disk, connections | > 80% sustained |

### Observability Stack
```
Logs:     stdout → collector (Fluentd/Vector) → storage (Loki/Elasticsearch)
Metrics:  app → Prometheus/OTEL → Grafana dashboards
Traces:   OpenTelemetry SDK → Jaeger/Tempo → distributed trace view
Alerts:   Grafana/PagerDuty → on-call rotation → runbook
```

### Structured Logging
```typescript
// Every log entry must have:
const log = {
  timestamp: new Date().toISOString(),
  level: 'error',
  service: 'payment-api',
  traceId: req.headers['x-trace-id'],
  message: 'Payment failed',
  error: { code: 'CARD_DECLINED', provider: 'stripe' },
  duration_ms: 1250,
  userId: req.user?.id, // never log PII in plain text
};
```

### Health Check Endpoint
```typescript
app.get('/health', async (req, res) => {
  const checks = {
    database: await checkDb().catch(() => false),
    redis: await checkRedis().catch(() => false),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
  };
  const healthy = checks.database && checks.redis;
  res.status(healthy ? 200 : 503).json({ status: healthy ? 'ok' : 'degraded', checks });
});
```

---

## Dockerfile Optimization Tips

| Optimization | Impact |
|-------------|--------|
| Multi-stage builds | 60-80% smaller images |
| Alpine base | ~5MB vs ~100MB for full Debian |
| `npm ci --only=production` in final stage | No devDependencies in image |
| Copy package files before source | Better layer caching |
| Combine RUN commands | Fewer layers, smaller image |
| Use `.dockerignore` | Faster build context transfer |
| Pin versions | Reproducible builds |
| `--no-cache` for security updates | Fresh packages in CI |

---

## Anti-Patterns

| ❌ Don't | ✅ Do Instead |
|----------|---------------|
| Run as root in container | `USER nonroot` or `USER 1000` |
| Store state in container filesystem | External volumes or object storage |
| Use `latest` tag in production | Pin specific version/SHA |
| Manual deployments | Automated CI/CD pipeline |
| Alert on every metric | Alert on symptoms (error rate), not causes (CPU) |
| SSH into production containers | Immutable infrastructure, redeploy |
| Shared credentials across environments | Per-environment secrets with rotation |
| Skip health checks | Always define HEALTHCHECK + readiness/liveness probes |
| Deploy on Friday | Deploy anytime with proper rollback + monitoring |
| Monolithic CI pipeline (30+ min) | Parallel jobs, caching, affected-only |

---

## Verification Checklist

Before considering DevOps work done:
- [ ] Dockerfile uses multi-stage build with non-root user
- [ ] `.dockerignore` excludes unnecessary files
- [ ] Health check endpoint exists and is used by orchestrator
- [ ] CI pipeline runs: lint, typecheck, test, security scan, build
- [ ] Deployment is automated (no manual steps)
- [ ] Rollback procedure documented and tested
- [ ] Secrets managed via environment/secret manager (not in code/image)
- [ ] Monitoring covers: latency, errors, traffic, saturation
- [ ] Alerts are actionable with runbook links
- [ ] Graceful shutdown handles SIGTERM (drain connections)
- [ ] Database migrations are backward-compatible
- [ ] Container images are scanned for vulnerabilities (Trivy/Snyk)

---

## MCP Integration

| Tool | Use For |
|------|---------|
| `bash` | Run Docker builds, test pipelines locally, check container logs |
| `context7` | Look up Docker, Kubernetes, Terraform docs |
| `grep` | Find hardcoded secrets, missing health checks, `latest` tags |
| `sequential-thinking` | Design deployment strategies, incident response plans |
| `playwright` | Smoke tests after deployment |

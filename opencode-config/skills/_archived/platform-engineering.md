# Skill: Platform Engineering
# Loaded on-demand when task involves Kubernetes, Helm, GitOps, service mesh, IaC, or secrets management

## Auto-Detect

Trigger this skill when:
- Task mentions: Kubernetes, k8s, Helm, ArgoCD, Flux, Terraform, Pulumi, Istio, Linkerd
- Files: `*.tf`, `Pulumi.*`, `helmfile.yaml`, `Chart.yaml`, `kustomization.yaml`
- Patterns: infrastructure as code, GitOps, service mesh, platform team
- `package.json` contains: `@pulumi/*`, `cdk8s`

---

## Decision Tree: IaC Tool Selection

```
What are you managing?
├── Cloud infrastructure (AWS/GCP/Azure)?
│   ├── Multi-cloud or cloud-agnostic? → Terraform (HCL, largest provider ecosystem)
│   ├── Want real programming language? → Pulumi (TypeScript/Python/Go)
│   ├── AWS-only, want tight integration? → AWS CDK (TypeScript/Python)
│   └── Simple, few resources? → Terraform (still, for ecosystem)
├── Kubernetes resources?
│   ├── Standard manifests with templating? → Helm
│   ├── Composition + overlays? → Kustomize
│   ├── Type-safe, programmatic? → cdk8s / Pulumi Kubernetes
│   └── GitOps delivery? → ArgoCD (Helm/Kustomize) or Flux
└── Both cloud + k8s?
    ├── Unified tool? → Pulumi (handles both natively)
    └── Separate concerns? → Terraform (infra) + ArgoCD (k8s workloads)
```

---

## Terraform Patterns

```hcl
# Module structure
# modules/
#   vpc/
#   eks/
#   rds/
# environments/
#   dev/
#   staging/
#   production/

# Good: Composable modules with clear interfaces
module "vpc" {
  source = "../../modules/vpc"

  environment    = var.environment
  cidr_block     = "10.0.0.0/16"
  azs            = ["us-east-1a", "us-east-1b", "us-east-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  tags = local.common_tags
}

module "eks" {
  source = "../../modules/eks"

  cluster_name    = "${var.project}-${var.environment}"
  cluster_version = "1.29"
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnet_ids

  node_groups = {
    general = {
      instance_types = ["m6i.xlarge"]
      min_size       = 3
      max_size       = 10
      desired_size   = 3
    }
    spot = {
      instance_types = ["m6i.xlarge", "m5.xlarge", "m5a.xlarge"]
      capacity_type  = "SPOT"
      min_size       = 0
      max_size       = 20
      desired_size   = 2
    }
  }

  tags = local.common_tags
}

# State management — ALWAYS remote with locking
terraform {
  backend "s3" {
    bucket         = "mycompany-terraform-state"
    key            = "environments/production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

### Terraform Anti-Patterns

| Anti-Pattern | Fix |
|---|---|
| Monolithic state file | Split into modules/layers (network, compute, data) |
| Hardcoded values | Use variables with validation blocks |
| No state locking | Always use DynamoDB/GCS/Azure Blob for locks |
| `terraform apply` without plan | Always `plan -out=tfplan` then `apply tfplan` |
| Secrets in `.tf` files | Use `data` sources from Vault/SSM/Secrets Manager |
| No module versioning | Pin module versions: `source = "git::...?ref=v1.2.3"` |

---

## Kubernetes Patterns

```yaml
# Production-ready deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  labels:
    app.kubernetes.io/name: order-service
    app.kubernetes.io/version: "1.4.2"
    app.kubernetes.io/managed-by: argocd
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # Zero-downtime deploys
  selector:
    matchLabels:
      app.kubernetes.io/name: order-service
  template:
    metadata:
      labels:
        app.kubernetes.io/name: order-service
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
    spec:
      serviceAccountName: order-service
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: order-service
          image: registry.example.com/order-service:1.4.2
          ports:
            - containerPort: 8080
              name: http
            - containerPort: 9090
              name: metrics
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: 1000m
              memory: 1Gi
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 15
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
          startupProbe:
            httpGet:
              path: /healthz
              port: http
            failureThreshold: 30
            periodSeconds: 2
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: order-service-secrets
                  key: database-url
          volumeMounts:
            - name: config
              mountPath: /etc/config
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: order-service-config
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: order-service
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: order-service
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: order-service
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: order-service
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: order-service
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "1000"
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
```

---

## GitOps with ArgoCD

```yaml
# Application definition
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: order-service
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: production
  source:
    repoURL: https://github.com/myorg/k8s-manifests.git
    targetRevision: main
    path: apps/order-service/overlays/production
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - PruneLast=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas  # Managed by HPA
```

### GitOps Repository Structure

```
k8s-manifests/
├── apps/
│   ├── order-service/
│   │   ├── base/
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   ├── hpa.yaml
│   │   │   └── kustomization.yaml
│   │   └── overlays/
│   │       ├── dev/
│   │       │   ├── kustomization.yaml
│   │       │   └── patches/
│   │       ├── staging/
│   │       └── production/
│   └── payment-service/
├── infrastructure/
│   ├── cert-manager/
│   ├── ingress-nginx/
│   ├── prometheus-stack/
│   └── sealed-secrets/
└── projects/
    ├── production.yaml
    └── staging.yaml
```

---

## Secrets Management

```
Decision Tree: Secrets in Kubernetes
├── Simple, few secrets? → Sealed Secrets (encrypt in git, decrypt in cluster)
├── Need rotation + audit? → External Secrets Operator + Vault/AWS SM
├── Need dynamic secrets? → HashiCorp Vault (database creds, PKI)
└── Cloud-native? → AWS Secrets Manager / GCP Secret Manager + ESO

NEVER:
- Store secrets in plain text in git
- Use ConfigMaps for sensitive data
- Hardcode secrets in container images
- Share secrets across environments
```

```yaml
# External Secrets Operator — sync from AWS Secrets Manager
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: order-service-secrets
  namespace: production
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: order-service-secrets
    creationPolicy: Owner
  data:
    - secretKey: database-url
      remoteRef:
        key: production/order-service/database
        property: url
    - secretKey: api-key
      remoteRef:
        key: production/order-service/api-keys
        property: payment-gateway
```

---

## Service Mesh (Istio)

```yaml
# Traffic management — canary deployment
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: order-service
spec:
  hosts:
    - order-service
  http:
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: order-service
            subset: canary
    - route:
        - destination:
            host: order-service
            subset: stable
          weight: 95
        - destination:
            host: order-service
            subset: canary
          weight: 5
---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: order-service
spec:
  host: order-service
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        h2UpgradePolicy: UPGRADE
        http1MaxPendingRequests: 100
        http2MaxRequests: 1000
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
  subsets:
    - name: stable
      labels:
        version: v1
    - name: canary
      labels:
        version: v2
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| ClickOps (manual console changes) | Drift, no audit trail, not reproducible | Everything as code, GitOps |
| Snowflake clusters | Each env is different, "works on my cluster" | Identical infra via IaC, only config differs |
| No resource limits | Noisy neighbor, OOM kills, cluster instability | Always set requests AND limits |
| Secrets in git (even "encrypted") | One leak exposes everything | External secrets operator + vault |
| No PDB | Voluntary disruptions kill availability | PodDisruptionBudget on every production workload |
| Single replica in prod | Any restart = downtime | Minimum 3 replicas with topology spread |
| No health probes | K8s routes to unhealthy pods | Liveness + readiness + startup probes |
| Helm values sprawl | 500-line values.yaml nobody understands | Kustomize overlays or Pulumi for complex cases |

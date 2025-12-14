# Kubernetes Deployment

This directory contains Kubernetes manifests for deploying Knowledge Mapper using [Kustomize](https://kustomize.io/).

## Directory Structure

```
k8s/
  base/                     # Base configuration (common to all environments)
    kustomization.yaml      # Kustomize configuration
    namespace.yaml          # Namespace definition with pod security
    configmap.yaml          # Non-sensitive configuration
    secret.yaml             # Secret template (references only)
    backend-deployment.yaml # Backend pods with health probes
    backend-service.yaml    # Backend ClusterIP service
    frontend-deployment.yaml# Frontend pods with nginx
    frontend-service.yaml   # Frontend ClusterIP service
    ingress.yaml            # Ingress with TLS configuration
  overlays/
    staging/                # Staging environment overrides
    production/             # Production environment overrides
  README.md                 # This file
```

## Prerequisites

### Cluster Requirements

- **Kubernetes**: 1.25+ (for pod security standards)
- **kubectl**: Configured with cluster access
- **Kustomize**: Built into kubectl 1.14+ or standalone

### Required Infrastructure

Before deploying, ensure you have:

1. **Container Registry**: Images pushed to a registry (e.g., ghcr.io)
2. **PostgreSQL Database**: Managed database service recommended
3. **Redis Instance**: For caching and sessions
4. **OAuth Provider**: Keycloak or compatible OIDC provider
5. **Ingress Controller**: nginx-ingress recommended
6. **cert-manager** (optional): For automatic TLS certificates

### Image References

Update image references in base manifests or overlays:

```yaml
# k8s/base/backend-deployment.yaml
image: ghcr.io/your-github-username/knowledge-mapper-backend:latest

# k8s/base/frontend-deployment.yaml
image: ghcr.io/your-github-username/knowledge-mapper-frontend:latest
```

## Quick Start

### 1. Create Namespace and Secrets

```bash
# Create namespace
kubectl create namespace knowledge-mapper

# Create secrets (replace with actual values)
kubectl create secret generic knowledge-mapper-secrets \
  --namespace knowledge-mapper \
  --from-literal=DATABASE_URL='postgresql+asyncpg://user:password@host:5432/db' \
  --from-literal=MIGRATION_DATABASE_URL='postgresql+asyncpg://migrator:password@host:5432/db' \
  --from-literal=REDIS_URL='redis://default:password@host:6379/0'
```

### 2. Validate Manifests

```bash
# Dry-run validation (client-side)
kubectl apply -k k8s/base --dry-run=client

# Server-side validation (checks deprecated APIs, admission webhooks)
kubectl apply -k k8s/base --dry-run=server

# Build and review rendered manifests
kubectl kustomize k8s/base
```

### 3. Deploy

```bash
# Deploy base configuration (development/testing only)
kubectl apply -k k8s/base

# Deploy staging overlay (recommended)
kubectl apply -k k8s/overlays/staging

# Deploy production overlay
kubectl apply -k k8s/overlays/production
```

### 4. Verify Deployment

```bash
# Check all resources
kubectl get all -n knowledge-mapper

# Check pod status
kubectl get pods -n knowledge-mapper -w

# Check deployment rollout
kubectl rollout status deployment/backend -n knowledge-mapper
kubectl rollout status deployment/frontend -n knowledge-mapper

# Check ingress
kubectl get ingress -n knowledge-mapper
```

## Configuration

### Environment Variables

#### ConfigMap (Non-sensitive)

Edit `k8s/base/configmap.yaml` or override in overlays:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENV` | Environment name | `production` |
| `LOG_LEVEL` | Logging level | `info` |
| `DEBUG` | Debug mode | `false` |
| `API_V1_PREFIX` | API path prefix | `/api/v1` |
| `OAUTH_ISSUER_URL` | Keycloak realm URL | Update for your deployment |
| `OTEL_SERVICE_NAME` | OpenTelemetry service name | `backend` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | `http://tempo.observability:4317` |

#### Secrets (Sensitive)

Create secrets manually or use external secret management:

| Secret Key | Description | Format |
|------------|-------------|--------|
| `DATABASE_URL` | Application database URL | `postgresql+asyncpg://user:pass@host:5432/db` |
| `MIGRATION_DATABASE_URL` | Migration database URL | `postgresql+asyncpg://migrator:pass@host:5432/db` |
| `REDIS_URL` | Redis connection URL | `redis://default:pass@host:6379/0` |


### Customization with Overlays

Create environment-specific overlays:

```yaml
# k8s/overlays/staging/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: knowledge-mapper-staging

resources:
  - ../../base

# Override ConfigMap values
configMapGenerator:
  - name: knowledge-mapper-config
    behavior: merge
    literals:
      - ENV=staging
      - LOG_LEVEL=debug
      - OAUTH_ISSUER_URL=https://auth-staging.example.com/realms/knowledge-mapper-dev

# Override image tags
images:
  - name: ghcr.io/your-github-username/knowledge-mapper-backend
    newTag: staging-abc123
  - name: ghcr.io/your-github-username/knowledge-mapper-frontend
    newTag: staging-abc123

# Override replicas
replicas:
  - name: backend
    count: 1
  - name: frontend
    count: 1

# Patches for staging-specific changes
patches:
  - target:
      kind: Ingress
      name: knowledge-mapper-ingress
    patch: |-
      - op: replace
        path: /spec/rules/0/host
        value: app-staging.example.com
      - op: replace
        path: /spec/rules/1/host
        value: api-staging.example.com
      - op: replace
        path: /spec/tls/0/hosts
        value:
          - app-staging.example.com
          - api-staging.example.com
```

## Operations

### Update Images

```bash
# Using kubectl set image
kubectl set image deployment/backend \
  backend=ghcr.io/your-github-username/knowledge-mapper-backend:v1.2.3 \
  -n knowledge-mapper

# Using Kustomize overlay (recommended)
# Update images[].newTag in overlay kustomization.yaml
kubectl apply -k k8s/overlays/staging
```

### Rollback

```bash
# View rollout history
kubectl rollout history deployment/backend -n knowledge-mapper

# Rollback to previous version
kubectl rollout undo deployment/backend -n knowledge-mapper

# Rollback to specific revision
kubectl rollout undo deployment/backend --to-revision=2 -n knowledge-mapper
```

### Scale

```bash
# Manual scaling
kubectl scale deployment/backend --replicas=5 -n knowledge-mapper

# For production, consider HPA (Horizontal Pod Autoscaler)
```

### View Logs

```bash
# Backend logs
kubectl logs -n knowledge-mapper -l app.kubernetes.io/component=backend -f

# Frontend logs
kubectl logs -n knowledge-mapper -l app.kubernetes.io/component=frontend -f

# Specific pod logs
kubectl logs -n knowledge-mapper backend-xxxxx-xxxxx -f
```

### Port Forwarding

```bash
# Access backend locally
kubectl port-forward -n knowledge-mapper svc/backend 8000:8000

# Access frontend locally
kubectl port-forward -n knowledge-mapper svc/frontend 8080:80

# Then access:
# Backend: http://localhost:8000/api/v1/health
# Frontend: http://localhost:8080
```

### Execute Commands in Pods

```bash
# Shell into backend pod
kubectl exec -it -n knowledge-mapper deploy/backend -- /bin/sh

# Run database migrations
kubectl exec -it -n knowledge-mapper deploy/backend -- \
  uv run alembic upgrade head
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod events
kubectl describe pod -n knowledge-mapper <pod-name>

# Check pod logs
kubectl logs -n knowledge-mapper <pod-name> --previous

# Common issues:
# - ImagePullBackOff: Check image name, registry access, pull secrets
# - CrashLoopBackOff: Check logs, health probe paths, resource limits
# - Pending: Check node resources, affinity rules, PVC binding
```

### Health Check Failures

```bash
# Check probe endpoints manually
kubectl exec -it -n knowledge-mapper deploy/backend -- \
  curl -v http://localhost:8000/api/v1/health

kubectl exec -it -n knowledge-mapper deploy/frontend -- \
  wget -q -O - http://localhost:8080/health
```

### Ingress Not Working

```bash
# Check ingress controller
kubectl get pods -n ingress-nginx

# Check ingress status
kubectl describe ingress -n knowledge-mapper

# Check TLS certificate
kubectl get certificate -n knowledge-mapper
kubectl describe certificate knowledge-mapper-tls -n knowledge-mapper
```

### Database Connection Issues

```bash
# Verify secret values
kubectl get secret knowledge-mapper-secrets -n knowledge-mapper -o yaml

# Test connectivity from pod
kubectl exec -it -n knowledge-mapper deploy/backend -- \
  nc -zv <db-host> 5432

# Check environment variables
kubectl exec -it -n knowledge-mapper deploy/backend -- env | grep DATABASE
```

## Security Best Practices

### Pod Security

All deployments follow Kubernetes security best practices:

- **runAsNonRoot**: Containers run as non-root user (UID 1000)
- **readOnlyRootFilesystem**: Root filesystem is read-only
- **allowPrivilegeEscalation: false**: No privilege escalation
- **capabilities.drop: ALL**: All Linux capabilities dropped
- **seccompProfile: RuntimeDefault**: Default seccomp profile applied

### Secret Management

**DO NOT commit secrets to git!** Use one of these approaches:

1. **External Secrets Operator**: [external-secrets.io](https://external-secrets.io/)
   ```yaml
   apiVersion: external-secrets.io/v1beta1
   kind: ExternalSecret
   metadata:
     name: knowledge-mapper-secrets
   spec:
     secretStoreRef:
       name: aws-secrets-manager
       kind: ClusterSecretStore
     target:
       name: knowledge-mapper-secrets
     data:
       - secretKey: DATABASE_URL
         remoteRef:
           key: knowledge-mapper/database-url
   ```

2. **Sealed Secrets**: [sealed-secrets](https://github.com/bitnami-labs/sealed-secrets)
   ```bash
   # Encrypt secrets for git storage
   kubeseal --format=yaml < secret.yaml > sealed-secret.yaml
   ```

3. **HashiCorp Vault**: [vault.io](https://www.vaultproject.io/)
   - Vault Agent Sidecar for secret injection
   - Vault CSI Provider for volume-mounted secrets

### Network Policies (Future Enhancement)

Consider implementing network policies to restrict pod-to-pod traffic:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-network-policy
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: backend
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/component: frontend
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
  egress:
    - to:
        - ipBlock:
            cidr: 10.0.0.0/8  # Internal cluster
    - ports:
        - port: 5432  # PostgreSQL
        - port: 6379  # Redis
```

## Resource Estimates

### Base Configuration

| Component | CPU Request | Memory Request | CPU Limit | Memory Limit | Replicas |
|-----------|-------------|----------------|-----------|--------------|----------|
| Backend   | 100m        | 256Mi          | 500m      | 512Mi        | 2        |
| Frontend  | 50m         | 64Mi           | 200m      | 128Mi        | 2        |
| **Total** | **300m**    | **640Mi**      | **1400m** | **1280Mi**   | 4        |

### Production Recommendations

For production workloads, consider:

1. **Horizontal Pod Autoscaler (HPA)**:
   ```yaml
   apiVersion: autoscaling/v2
   kind: HorizontalPodAutoscaler
   metadata:
     name: backend-hpa
   spec:
     scaleTargetRef:
       apiVersion: apps/v1
       kind: Deployment
       name: backend
     minReplicas: 2
     maxReplicas: 10
     metrics:
       - type: Resource
         resource:
           name: cpu
           target:
             type: Utilization
             averageUtilization: 70
   ```

2. **Pod Disruption Budget (PDB)**:
   ```yaml
   apiVersion: policy/v1
   kind: PodDisruptionBudget
   metadata:
     name: backend-pdb
   spec:
     minAvailable: 1
     selector:
       matchLabels:
         app.kubernetes.io/component: backend
   ```

## CI/CD Deployment

For automated deployments using GitHub Actions, see [Deployment Guide](../docs/DEPLOYMENT.md).

The deployment workflow provides:
- Automatic staging deployment on merge to main
- Production deployment on version tags with manual approval
- Kustomize-based image tag updates
- Deployment verification and rollback procedures

## Additional Resources

- [Deployment Guide](../docs/DEPLOYMENT.md)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Kustomize Documentation](https://kustomize.io/)
- [nginx-ingress](https://kubernetes.github.io/ingress-nginx/)
- [cert-manager](https://cert-manager.io/docs/)
- [External Secrets Operator](https://external-secrets.io/)

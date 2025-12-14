# Deployment Guide

This document describes the deployment process for Knowledge Mapper using GitHub Actions and Kubernetes.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [GitHub Environment Setup](#github-environment-setup)
- [Deployment Workflows](#deployment-workflows)
- [Rollback Procedures](#rollback-procedures)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)

## Overview

The deployment workflow uses:

- **GitHub Actions** for CI/CD automation
- **Kustomize** for Kubernetes manifest management
- **GitHub Environments** for deployment protection and secrets management

### Deployment Flow

```
                 +----------------+
                 |   Code Push    |
                 +-------+--------+
                         |
                         v
                 +----------------+
                 |  Build (CI)    |
                 |  - Tests       |
                 |  - Container   |
                 +-------+--------+
                         |
         +---------------+---------------+
         |                               |
         v                               v
+--------+--------+             +--------+--------+
|    Staging      |             |   Production    |
|  (Auto-deploy)  |             | (Manual/Tag)    |
+-----------------+             +-----------------+
```

## Prerequisites

### 1. Kubernetes Cluster

Each environment requires a Kubernetes cluster with:

- **Kubernetes 1.25+** (for Pod Security Standards)
- **Ingress Controller** (nginx-ingress recommended)
- **cert-manager** (optional, for automatic TLS)
- Appropriate RBAC permissions for the deployment service account

### 2. Container Registry

Images are pushed to GitHub Container Registry (ghcr.io) during the build workflow.

### 3. External Dependencies

Ensure these are provisioned before deployment:

- **PostgreSQL** database (managed service recommended)
- **Redis** instance for caching and sessions
- **OAuth Provider** (Keycloak or compatible OIDC provider)

## GitHub Environment Setup

### Creating Environments

1. Navigate to your repository on GitHub
2. Go to **Settings** > **Environments**
3. Create two environments: `staging` and `production`

### Staging Environment Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| **Required reviewers** | None | Auto-deploy without approval |
| **Wait timer** | 0 minutes | No delay |
| **Deployment branches** | `main` only | Restrict to main branch |

**Secrets:**

| Secret Name | Description | How to Generate |
|-------------|-------------|-----------------|
| `KUBECONFIG_STAGING` | Base64-encoded kubeconfig for staging cluster | See [Creating Kubeconfig Secret](#creating-kubeconfig-secret) |

### Production Environment Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| **Required reviewers** | 1-6 team members | Manual approval required |
| **Wait timer** | 0-30 minutes (optional) | Time for review before deployment |
| **Deployment branches** | `main` and version tags (`v*`) | Restrict to releases |

**Secrets:**

| Secret Name | Description | How to Generate |
|-------------|-------------|-----------------|
| `KUBECONFIG_PRODUCTION` | Base64-encoded kubeconfig for production cluster | See [Creating Kubeconfig Secret](#creating-kubeconfig-secret) |

### Creating Kubeconfig Secret

```bash
# 1. Get kubeconfig from your cluster
# For a specific context:
kubectl config view --minify --flatten --context=your-context > kubeconfig.yaml

# 2. Base64 encode the kubeconfig
base64 -w 0 kubeconfig.yaml > kubeconfig.b64

# 3. Copy the content of kubeconfig.b64

# 4. Add to GitHub:
#    Settings > Environments > [environment] > Add secret
#    Name: KUBECONFIG_STAGING or KUBECONFIG_PRODUCTION
#    Value: [paste base64 content]

# 5. Clean up local files
rm kubeconfig.yaml kubeconfig.b64
```

### Alternative: Cloud Provider OIDC

For enhanced security, use OIDC authentication instead of static kubeconfig:

#### AWS EKS

1. Create an IAM OIDC identity provider for your cluster
2. Create an IAM role with trust policy for GitHub Actions
3. Add role ARN as secret: `AWS_ROLE_ARN_STAGING` / `AWS_ROLE_ARN_PRODUCTION`

```yaml
# In deploy.yml, replace kubeconfig configuration with:
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_ARN_STAGING }}
    aws-region: us-east-1
- run: aws eks update-kubeconfig --name cluster-name --region us-east-1
```

#### Google GKE

1. Enable Workload Identity Federation
2. Create a service account with GKE permissions
3. Add secrets: `GCP_WORKLOAD_IDENTITY_STAGING`, `GCP_SERVICE_ACCOUNT_STAGING`

```yaml
# In deploy.yml, replace kubeconfig configuration with:
- uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_STAGING }}
    service_account: ${{ secrets.GCP_SERVICE_ACCOUNT_STAGING }}
- uses: google-github-actions/get-gke-credentials@v2
  with:
    cluster_name: cluster-name
    location: us-central1
```

## Deployment Workflows

### Automatic Staging Deployment

Staging deploys automatically when:

1. Code is merged to `main` branch
2. The Build workflow completes successfully

**Flow:**
```
Push to main -> Build workflow -> Deploy workflow (staging)
```

### Manual Deployment

Trigger deployments manually via GitHub Actions UI:

1. Go to **Actions** > **Deploy**
2. Click **Run workflow**
3. Select:
   - **Environment**: `staging` or `production`
   - **Image tag**: Specific version (e.g., `1.2.3`) or leave empty for `latest`
4. Click **Run workflow**

### Production Release Deployment

Production deploys when a version tag is pushed:

```bash
# Create and push a version tag
git tag v1.2.3
git push origin v1.2.3
```

This triggers:
1. Build workflow (creates images tagged with version)
2. Deploy workflow (requires approval for production environment)
3. GitHub Release creation (with auto-generated release notes)

### Deployment Verification

After deployment, the workflow verifies:

1. **Rollout Status**: Waits for deployment to complete
2. **Pod Readiness**: Ensures all pods are ready
3. **Health Check**: Verifies backend health endpoint responds

Skip verification with the `skip_verification` input (for emergencies only).

## Rollback Procedures

### Quick Rollback (kubectl)

Roll back to the previous version:

```bash
# Rollback backend
kubectl rollout undo deployment/backend -n knowledge-mapper

# Rollback frontend
kubectl rollout undo deployment/frontend -n knowledge-mapper

# Verify rollback status
kubectl rollout status deployment/backend -n knowledge-mapper
```

### Rollback to Specific Revision

```bash
# List revision history
kubectl rollout history deployment/backend -n knowledge-mapper

# Output example:
# REVISION  CHANGE-CAUSE
# 1         Initial deployment
# 2         Update to v1.1.0
# 3         Update to v1.2.0

# Rollback to revision 2
kubectl rollout undo deployment/backend -n knowledge-mapper --to-revision=2
```

### Rollback via Workflow

1. Go to **Actions** > **Deploy**
2. Click **Run workflow**
3. Select target environment
4. Enter the previous working image tag (e.g., `1.1.0`)
5. Click **Run workflow**

### Emergency Rollback Checklist

- [ ] Identify the last known good version
- [ ] Notify team of rollback
- [ ] Execute rollback (kubectl or workflow)
- [ ] Verify health endpoints
- [ ] Monitor error rates and logs
- [ ] Create incident report

## Troubleshooting

### Deployment Fails to Start

**Symptom**: Workflow fails at "Configure Kubernetes credentials"

**Solutions**:
1. Verify `KUBECONFIG_*` secret is properly base64 encoded
2. Check cluster is accessible from GitHub Actions
3. Verify kubeconfig context is correct

```bash
# Test kubeconfig locally
export KUBECONFIG=/path/to/kubeconfig.yaml
kubectl cluster-info
```

### Pods Not Starting

**Symptom**: Pods stuck in `Pending`, `ImagePullBackOff`, or `CrashLoopBackOff`

**ImagePullBackOff**:
```bash
# Check if image exists
docker pull ghcr.io/your-github-username/knowledge-mapper-backend:TAG

# Verify pull secret (if using private registry)
kubectl get secret -n knowledge-mapper
```

**CrashLoopBackOff**:
```bash
# Check pod logs
kubectl logs -n knowledge-mapper -l app.kubernetes.io/component=backend --previous

# Check events
kubectl describe pod -n knowledge-mapper -l app.kubernetes.io/component=backend
```

### Health Checks Failing

**Symptom**: Deployment verification fails at health check

```bash
# Test health endpoint manually
kubectl port-forward -n knowledge-mapper svc/backend 8000:8000
curl http://localhost:8000/api/v1/health

# Check if endpoint is correct in deployment
kubectl get deployment backend -n knowledge-mapper -o yaml | grep -A5 livenessProbe
```

### Rollout Timeout

**Symptom**: "Waiting for deployment rollout" times out

```bash
# Check deployment status
kubectl get deployment -n knowledge-mapper

# Check events for issues
kubectl get events -n knowledge-mapper --sort-by='.lastTimestamp'

# Check resource availability
kubectl describe nodes | grep -A5 "Allocated resources"
```

## Security Considerations

### Secrets Management

**DO NOT**:
- Commit secrets to git
- Log secrets in workflow output
- Use long-lived credentials when OIDC is available

**DO**:
- Use GitHub Environment secrets
- Rotate credentials regularly
- Use cloud provider OIDC for production
- Limit secret access by environment

### RBAC for Deployment

Create a dedicated service account with minimal permissions:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: github-actions-deploy
  namespace: knowledge-mapper
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: github-actions-deploy
  namespace: knowledge-mapper
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: [""]
    resources: ["pods", "pods/exec", "pods/log"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["configmaps", "secrets", "services"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: github-actions-deploy
  namespace: knowledge-mapper
subjects:
  - kind: ServiceAccount
    name: github-actions-deploy
    namespace: knowledge-mapper
roleRef:
  kind: Role
  name: github-actions-deploy
  apiGroup: rbac.authorization.k8s.io
```

### Network Security

Consider implementing:

1. **Network Policies** to restrict pod-to-pod traffic
2. **Ingress TLS** with cert-manager
3. **Pod Security Standards** (already configured in namespace)

### Audit Trail

The deployment workflow creates:

- **Commit status** for each deployment
- **GitHub Release** for production tags
- **Workflow run logs** (retained per org settings)

## Monitoring Deployments

### GitHub Actions

- View deployment status in **Actions** tab
- Check **Environments** for deployment history
- Review **Releases** for production deployments

### Kubernetes Metrics

After deployment, monitor via Prometheus/Grafana:

```promql
# Deployment replica status
kube_deployment_status_replicas_available{namespace="knowledge-mapper"}

# Pod restart count (should be 0 after healthy deployment)
increase(kube_pod_container_status_restarts_total{namespace="knowledge-mapper"}[1h])

# Request success rate
sum(rate(http_requests_total{namespace="knowledge-mapper", status!~"5.."}[5m])) /
sum(rate(http_requests_total{namespace="knowledge-mapper"}[5m]))
```

### Alerting

Consider alerts for:

- Deployment failures (GitHub webhook to Slack/PagerDuty)
- Pod restarts after deployment
- Error rate increase post-deployment
- Health check failures

## Related Documentation

- [Environment Configuration](./operations/environment-configuration.md) - Complete environment variable reference
- [Secrets Management](./operations/secrets-management.md) - Production secrets patterns (Vault, AWS SM, Sealed Secrets)
- [Configuration Validation](./operations/configuration-validation.md) - Troubleshooting guide
- [Kubernetes Manifests](../k8s/README.md)
- [Build Workflow](.github/workflows/build.yml)
- [CI Workflow](.github/workflows/ci.yml)

# ADR-021: Kubernetes Deployment Strategy

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2025-12-06 |
| **Decision Makers** | Project Team |
| **Related ADRs** | ADR-019 (GitHub Actions CI/CD) |

## Context

{{ cookiecutter.project_name }} needs a Kubernetes deployment strategy for staging and production environments. Key challenges include:

1. **Deployment Complexity**: Kubernetes has a steep learning curve; we need to balance power with accessibility
2. **Environment Variability**: Staging and production require different configurations (replicas, resources, domains)
3. **Template Compatibility**: Deployment manifests must work with cookiecutter templating
4. **Tooling Choices**: Multiple tools exist (Helm, Kustomize, raw YAML, Jsonnet, cdk8s)
5. **Operational Needs**: Must support rolling updates, health checks, and resource limits
6. **Optional Feature**: Not all projects need Kubernetes; it should be opt-in via `include_kubernetes`

The template already uses Docker Compose for development. Kubernetes is the target for production deployments where container orchestration, scaling, and high availability are required.

## Decision

We adopt **Kustomize with plain YAML manifests** for Kubernetes deployment, structured as:

```
k8s/
  base/                           # Common configuration
    kustomization.yaml
    namespace.yaml
    backend-deployment.yaml
    backend-service.yaml
    frontend-deployment.yaml
    frontend-service.yaml
    configmap.yaml
    secret.yaml
    ingress.yaml
  overlays/
    staging/                      # Staging overrides
      kustomization.yaml
      configmap-patch.yaml
      replicas-patch.yaml
      resources-patch.yaml
    production/                   # Production overrides
      kustomization.yaml
      configmap-patch.yaml
      replicas-patch.yaml
      resources-patch.yaml
      pdb.yaml
```

### Deployment Commands

```bash
# Staging
kubectl apply -k k8s/overlays/staging

# Production
kubectl apply -k k8s/overlays/production

# Preview rendered manifests
kubectl kustomize k8s/overlays/production
```

### Key Design Principles

1. **Plain YAML Base**: Human-readable, IDE-supported, easy to understand
2. **Kustomize Overlays**: Environment-specific patches without duplication
3. **No Templating in Manifests**: Cookiecutter handles project-level templating; Kustomize handles environment-level
4. **Security by Default**: Non-root containers, read-only filesystems, dropped capabilities
5. **Resource Limits**: All containers have requests and limits defined
6. **Health Probes**: Liveness, readiness, and startup probes for all services

### Security Context

All containers run with restrictive security contexts:

```yaml
securityContext:
  # Pod-level
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
  seccompProfile:
    type: RuntimeDefault

  # Container-level
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
```

This configuration:
- Prevents privilege escalation attacks
- Limits filesystem modification to mounted volumes only
- Drops all Linux capabilities (principle of least privilege)
- Uses seccomp profiles for system call filtering

### Optional Feature Pattern

The Kubernetes directory is conditionally included via cookiecutter:

```json
{
  "include_kubernetes": "no"
}
```

When disabled, the post-generation hook removes the `k8s/` directory entirely.

## Consequences

### Positive

1. **No Additional Tooling**: Kustomize is built into `kubectl` since v1.14
   ```bash
   # No installation needed
   kubectl apply -k k8s/overlays/production
   ```

2. **Simple Mental Model**: Base + Overlays is intuitive
   - Base: What is common to all environments
   - Overlay: What is different per environment

3. **GitOps Ready**: Plain YAML works with any GitOps tool
   ```yaml
   # Argo CD Application example
   spec:
     source:
       path: k8s/overlays/production
       kustomize:
         images:
           - ghcr.io/owner/backend=ghcr.io/owner/backend:v1.0.0
   ```

4. **IDE Support**: YAML files are well-supported by editors
   - Kubernetes YAML schema validation
   - Auto-completion for resource fields
   - No custom plugin required (unlike Helm)

5. **Debuggable**: Can preview exactly what will be applied
   ```bash
   kubectl kustomize k8s/overlays/production > rendered.yaml
   kubectl diff -k k8s/overlays/production
   ```

6. **Security Best Practices Built-In**:
   - Non-root containers (runAsNonRoot: true)
   - Read-only root filesystem
   - Dropped capabilities
   - Resource limits preventing noisy neighbor issues

7. **Production-Ready Defaults**:
   - Rolling update strategy with maxUnavailable: 0
   - Pod anti-affinity for availability
   - Health probes with appropriate timeouts

### Negative

1. **Limited Templating**: Kustomize patches are less flexible than Helm templates
   - Cannot conditionally include resources based on values
   - Complex transformations require multiple patches

2. **Overlay Duplication**: Similar patches may be repeated across overlays
   - Staging and production may have similar structure
   - Could extract common patterns to intermediate overlays

3. **No Package Management**: Unlike Helm, cannot version or share as packages
   - No chart repository concept
   - Harder to consume third-party applications

4. **Learning Curve**: Strategic merge patches and JSON patches require understanding
   - Patch semantics differ from simple value replacement
   - Debugging patch failures can be challenging

### Neutral

1. **Cookiecutter Compatibility**: Jinja2 templating in YAML works but requires care with brace escaping

2. **Upgrade Path**: Can migrate to Helm if needed
   - Extract manifests as Helm templates
   - Convert values to values.yaml

---

## Alternatives Considered

### Helm Charts

**Approach**: Use Helm for templating and packaging.

```yaml
# values.yaml
replicaCount: 3
image:
  repository: ghcr.io/owner/app
  tag: v1.0.0
```

**Strengths**:
- Powerful Go templating
- Package management (chart repositories)
- Large ecosystem of community charts
- Release management with rollback

**Why Not Chosen**:
- Requires Helm CLI installation
- Template syntax adds complexity ({{ .Values.x }})
- Conflicts with cookiecutter Jinja2 syntax (both use {{ }})
- Overkill for single-application deployment
- Debugging rendered templates is harder

**When to Reconsider**:
- Multiple applications sharing configuration
- Need to publish as reusable chart
- Complex conditional logic required
- Team already proficient with Helm

### Raw YAML (No Kustomize)

**Approach**: Separate complete YAML files per environment without any tooling.

```
k8s/
  staging/
    deployment.yaml
    service.yaml
    ingress.yaml
  production/
    deployment.yaml
    service.yaml
    ingress.yaml
```

**Strengths**:
- Maximum simplicity
- No tooling dependencies
- Easy to understand each environment independently

**Why Not Chosen**:
- Massive duplication across environments (DRY violation)
- Easy to miss updating one environment when making changes
- No drift detection between environments
- Maintenance burden increases with manifest count

### Jsonnet / cdk8s

**Approach**: Use a programming language for manifest generation.

```jsonnet
// deployment.jsonnet
local k = import 'k.libsonnet';
k.deployment.new('backend', 3, [...])
```

**Strengths**:
- Full programming language expressiveness
- Strong typing with type checking
- Functions, variables, and libraries
- Powerful abstraction capabilities

**Why Not Chosen**:
- Requires learning new language/framework
- Additional build step to generate YAML
- IDE support less mature than YAML
- Overkill for template scope
- Adds cognitive overhead for contributors

### Terraform Kubernetes Provider

**Approach**: Manage Kubernetes resources via Terraform alongside infrastructure.

```hcl
resource "kubernetes_deployment" "backend" {
  metadata { name = "backend" }
  spec { ... }
}
```

**Strengths**:
- Single tool for infrastructure and application
- State management and drift detection
- Integration with cloud infrastructure (VPCs, databases)

**Why Not Chosen**:
- Mixes infrastructure and application concerns
- State management complexity for applications
- Slower feedback loop for app changes
- Not standard Kubernetes workflow
- Terraform Kubernetes provider lags behind Kubernetes API

---

## Configuration Details

### Resource Defaults

| Component | Environment | CPU Request | Memory Request | CPU Limit | Memory Limit | Replicas |
|-----------|-------------|-------------|----------------|-----------|--------------|----------|
| Backend | Staging | 50m | 128Mi | 250m | 256Mi | 1 |
| Backend | Production | 200m | 512Mi | 1000m | 1Gi | 3 |
| Frontend | Staging | 25m | 32Mi | 100m | 64Mi | 1 |
| Frontend | Production | 100m | 128Mi | 500m | 256Mi | 2 |

### Health Probe Configuration

| Probe | Backend | Frontend |
|-------|---------|----------|
| Liveness Path | /api/v1/health | / |
| Readiness Path | /api/v1/health | / |
| Startup Initial Delay | 5s | 5s |
| Liveness Initial Delay | 30s | 10s |
| Readiness Initial Delay | 10s | 5s |
| Period | 10-30s | 10-30s |
| Timeout | 5-10s | 5s |
| Failure Threshold | 3 | 3 |

### Deployment Strategy

| Environment | Strategy | Max Surge | Max Unavailable |
|-------------|----------|-----------|-----------------|
| Staging | RollingUpdate | 1 | 1 |
| Production | RollingUpdate | 1 | 0 |

**Production Zero-Downtime**: With `maxUnavailable: 0`, at least the current number of pods are always available during updates.

---

## Related ADRs

- [ADR-019: GitHub Actions CI/CD](./ADR-019-github-actions-cicd.md) - Build workflow produces container images
- [ADR-022: Container Security Scanning](./ADR-022-container-security-scanning.md) - Trivy scans images before deployment

## Implementation References

- `k8s/base/` - Base manifests
- `k8s/overlays/staging/` - Staging overlay
- `k8s/overlays/production/` - Production overlay
- `k8s/README.md` - Deployment documentation
- `cookiecutter.json` - `include_kubernetes` variable

## External References

- [Kustomize Documentation](https://kustomize.io/)
- [Kubernetes Security Best Practices](https://kubernetes.io/docs/concepts/security/overview/)
- [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [GitOps with Kustomize](https://kubectl.docs.kubernetes.io/guides/config_management/)

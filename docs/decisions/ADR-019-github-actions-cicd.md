# ADR-019: GitHub Actions CI/CD

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2025-12-06 |
| **Decision Makers** | Project Team |

## Context

The project-starter template generates full-stack applications that require automated testing and container image building for production deployments. Key CI/CD requirements include:

1. **Automated Testing**: Run linting and tests on every pull request to catch issues before merge
2. **Container Image Building**: Build and publish multi-platform Docker images to a container registry
3. **Dependency Management**: Automate dependency updates with security scanning
4. **Code Coverage Tracking**: Track test coverage over time with PR-level feedback
5. **Matrix Testing**: Validate template generation across cookiecutter option combinations
6. **Zero-Config Experience**: Generated projects should have working CI/CD without additional setup

The template targets GitHub-hosted projects, making GitHub Actions the natural choice for CI/CD integration.

## Decision

We implement GitHub Actions as the CI/CD platform for generated projects, with two primary workflows and supporting configurations.

### Workflow Structure

**CI Workflow** (`.github/workflows/ci.yml`):
- Triggered on pull requests to `main`/`develop` and pushes to `main`
- Runs four parallel jobs for fast feedback:
  - `backend-lint`: Ruff linting and format checking
  - `backend-test`: Pytest with PostgreSQL and Redis service containers
  - `frontend-lint`: ESLint
  - `frontend-test`: Vitest with coverage

**Build Workflow** (`.github/workflows/build.yml`):
- Triggered on push to `main`, version tags (`v*`), and manual dispatch
- Builds multi-platform container images (linux/amd64, linux/arm64)
- Publishes to GitHub Container Registry (ghcr.io)
- Generates SBOM (Software Bill of Materials) for security scanning

### Key Actions Selected

| Action | Purpose | Version |
|--------|---------|---------|
| `actions/checkout@v4` | Repository checkout | v4 |
| `astral-sh/setup-uv@v4` | Python dependency management (aligns with ADR-012) | v4 |
| `actions/setup-node@v4` | Node.js and npm setup | v4 |
| `docker/setup-buildx-action@v3` | Multi-platform Docker builds | v3 |
| `docker/build-push-action@v6` | Build and push container images | v6 |
| `docker/metadata-action@v5` | OCI-compliant image tagging | v5 |
| `codecov/codecov-action@v5` | Coverage upload and reporting | v5 |
| `anchore/sbom-action@v0` | SBOM generation for supply chain security | v0 |

### Service Containers

Backend tests require database and cache services:

```yaml
services:
  postgres:
    image: postgres:{{ cookiecutter.postgres_version }}-alpine
    env:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: test_db
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5

  redis:
    image: redis:{{ cookiecutter.redis_version }}-alpine
    options: >-
      --health-cmd "redis-cli ping"
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
```

Health checks ensure services are ready before tests execute.

### Coverage Strategy

- **Codecov Integration**: Unified coverage reporting for backend and frontend
- **Coverage Flags**: Separate `backend` and `frontend` flags for component-level tracking
- **Fail-Open Upload**: `fail_ci_if_error: false` prevents Codecov outages from blocking deployments
- **Artifact Backup**: Coverage reports uploaded as workflow artifacts for debugging

### Container Image Tagging

The build workflow uses `docker/metadata-action` for consistent tagging:

| Trigger | Tags Generated |
|---------|---------------|
| Push to `main` | `latest`, `main`, `<sha>` |
| Tag `v1.2.3` | `1.2.3`, `1.2`, `<sha>` |
| Manual dispatch | `<branch>`, `<sha>` |

### Concurrency Control

Both workflows implement concurrency groups to cancel redundant runs:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

This saves GitHub Actions minutes and provides faster feedback on the latest commit.

### Cookiecutter Conditional Pattern

GitHub Actions workflows are conditionally included via `include_github_actions` variable, following the pattern established in ADR-017 for optional features:

```json
{
  "include_github_actions": "yes"
}
```

When disabled, the post-generation hook removes the `.github/` directory.

## Consequences

### Positive

1. **Zero-Config CI/CD**: Generated projects have working CI/CD immediately after creation, reducing time-to-production

2. **GitHub-Native Experience**: No external service accounts required. Uses built-in `GITHUB_TOKEN` for registry authentication

3. **Multi-Platform Builds**: ARM64 support enables deployment to Apple Silicon Macs and ARM-based cloud instances (AWS Graviton, etc.)

4. **Supply Chain Security**: SBOM generation enables vulnerability scanning and compliance reporting

5. **Automated Dependency Updates**: Dependabot configuration (P1-04) integrates with CI for automatic security patches

6. **Coverage Visibility**: Codecov provides PR comments with coverage diffs, encouraging test coverage improvements

7. **Fast Feedback**: Parallel jobs and concurrency control minimize wait times for developers

8. **Caching Optimization**: uv cache (`astral-sh/setup-uv` with cache) and Docker layer cache (`type=gha`) reduce build times

### Negative

1. **GitHub Lock-in**: Workflows are not portable to GitLab CI, Jenkins, or other CI platforms without rewriting

2. **Minutes Consumption**: Private repositories consume GitHub Actions minutes (free tier: 2,000 min/month for Pro, 3,000 min/month for Team)

3. **Self-Hosted Runner Requirements**: Private network access (internal registries, databases) requires self-hosted runners

4. **Limited Matrix Testing**: Full cookiecutter option matrix would explode CI time; only critical combinations can be tested

5. **Secrets Configuration**: `CODECOV_TOKEN` must be configured manually in repository secrets for private repos

### Neutral

1. **Branch Protection Complement**: CI status checks complement but don't replace branch protection rules. Repository owners must configure required status checks

2. **No Deployment Pipeline**: Build workflow publishes images but doesn't deploy. Deployment requires additional configuration (Kubernetes manifests, ArgoCD, etc.)

3. **Version Pinning Trade-offs**: Action versions are pinned for reproducibility but require periodic updates for security patches

## Alternatives Considered

### GitLab CI

**Approach**: Use GitLab CI/CD with `.gitlab-ci.yml` configuration.

**Strengths**:
- More powerful pipeline features (DAG, child pipelines)
- Built-in container registry
- Better self-hosted experience

**Why Not Chosen**:
- Template targets GitHub-hosted projects
- Would require GitLab hosting or repository mirroring
- Less relevant for GitHub-first workflows

### Jenkins

**Approach**: Use Jenkins with Jenkinsfile for pipeline definition.

**Strengths**:
- Highly customizable with extensive plugin ecosystem
- Self-hosted with full control
- Mature and battle-tested

**Why Not Chosen**:
- Requires separate infrastructure to deploy and maintain
- Higher operational overhead than managed CI
- Less aligned with modern developer-first workflows
- Configuration complexity (Groovy DSL) vs. YAML

### CircleCI / Travis CI

**Approach**: Use external CI service with GitHub integration.

**Strengths**:
- Powerful caching and parallelism
- Good Docker support
- Cross-platform builds

**Why Not Chosen**:
- External service dependency adds friction
- Requires additional account creation and configuration
- Less deep GitHub integration (no built-in secrets, GITHUB_TOKEN)
- Cost implications for private repositories

### No CI/CD (User Provides)

**Approach**: Let users configure their own CI/CD after project generation.

**Why Not Chosen**:
- Increases time-to-production significantly
- Leads to inconsistent CI implementations across projects
- Misses opportunity to establish best practices
- Template value proposition includes production-readiness

---

## Related ADRs

- [ADR-012: uv as Python Package Manager](./ADR-012-uv-package-manager.md) - Python dependency management in CI uses uv
- [ADR-016: Cookiecutter as Template Engine](./ADR-016-cookiecutter-template-engine.md) - Conditional inclusion pattern
- [ADR-017: Optional Observability Stack](./ADR-017-optional-observability-stack.md) - Pattern for optional features via `include_*` variables

## Implementation References

- `.github/workflows/ci.yml` - CI workflow (lint and test on PRs)
- `.github/workflows/build.yml` - Build workflow (container images on merge)
- `.github/dependabot.yml` - Automated dependency updates
- `backend/pyproject.toml` - Python dependencies and test configuration
- `frontend/package.json` - Node.js dependencies and test scripts

## External References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Actions Billing](https://docs.github.com/en/billing/managing-billing-for-github-actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
- [Codecov GitHub Action](https://github.com/codecov/codecov-action)

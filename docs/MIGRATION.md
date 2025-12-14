# Migration Guide

This guide helps you upgrade existing projects generated from earlier versions of the Knowledge Mapper template to include Production Essentials features.

## Table of Contents

1. [Version Compatibility](#version-compatibility)
2. [Pre-Migration Checklist](#pre-migration-checklist)
3. [Feature Migration Guides](#feature-migration-guides)
   - [CI/CD Pipeline](#cicd-pipeline)
   - [Security Hardening](#security-hardening)
   - [Operational Readiness](#operational-readiness)
   - [Kubernetes Deployment](#kubernetes-deployment)
   - [Developer Experience](#developer-experience)
4. [Post-Migration Verification](#post-migration-verification)
5. [Troubleshooting](#troubleshooting)
6. [Rollback Procedures](#rollback-procedures)

---

## Version Compatibility

### Feature Requirements

| Feature | Minimum Template Version | Dependencies |
|---------|-------------------------|--------------|
| CI/CD Pipeline | 2.0.0 | GitHub repository |
| Security Headers | 2.0.0 | None |
| Secret Detection (Gitleaks) | 2.0.0 | pre-commit |
| Sentry Integration | 2.0.0 | `include_sentry=yes` |
| Kubernetes Manifests | 2.0.0 | `include_kubernetes=yes` |
| k6 Load Testing | 2.0.0 | k6 CLI installed |
| API Client Generation | 2.0.0 | OpenAPI Generator CLI |
| Database Backup/Restore | 2.0.0 | Docker |

### Breaking Changes in 2.0.0

1. **New cookiecutter variables added:**
   - `include_github_actions` - Enable/disable GitHub Actions workflows
   - `include_kubernetes` - Enable/disable Kubernetes manifests
   - `include_sentry` - Enable/disable Sentry error tracking
   - `github_username` - GitHub username/org for container registry

2. **Backend configuration additions:**
   - Security header settings in `backend/app/core/config.py`
   - Optional Sentry configuration
   - New middleware registration in `main.py`

3. **New middleware stack order:**
   - CORS middleware
   - Security headers middleware
   - Tenant context middleware

4. **Directory structure additions:**
   ```
   .github/
     workflows/
       ci.yml
       build.yml
       deploy.yml
       security.yml
     dependabot.yml
   k8s/
     base/
     overlays/
   tests/load/
   scripts/
     db-backup.sh
     db-restore.sh
     db-verify.sh
     generate-api-client.sh
     load-test.sh
   docs/
     runbooks/
     operations/
   ```

---

## Pre-Migration Checklist

Before starting migration, ensure:

- [ ] Current project is in a clean git state (no uncommitted changes)
- [ ] All tests pass in current state
- [ ] Database backup is available
- [ ] You have reviewed the breaking changes above
- [ ] Required environment variables are documented for your deployment
- [ ] You have access to the latest template repository

### Create Backup Branch

```bash
# Create a backup branch
git checkout -b pre-migration-backup
git push origin pre-migration-backup

# Return to main branch
git checkout main

# Create migration branch
git checkout -b feature/production-essentials-migration
```

### Generate Reference Project

Generate a fresh project with all features enabled for reference:

```bash
# Clone template repository
git clone https://github.com/your-org/project-starter.git /tmp/project-starter

# Generate reference project with all features
cd /tmp/project-starter
cookiecutter . --no-input \
  project_name="Reference Project" \
  project_slug="reference-project" \
  include_github_actions=yes \
  include_kubernetes=yes \
  include_sentry=yes \
  include_observability=yes

# Use this as reference for file contents
ls /tmp/reference-project/
```

---

## Feature Migration Guides

### CI/CD Pipeline

**Files to add:**
```
.github/
  workflows/
    ci.yml           # Continuous integration
    build.yml        # Docker image build
    deploy.yml       # Deployment automation
    security.yml     # Security scanning
  dependabot.yml     # Dependency updates
```

**Steps:**

1. **Create workflow directory:**
   ```bash
   mkdir -p .github/workflows
   ```

2. **Copy CI workflow (`ci.yml`):**

   Create `.github/workflows/ci.yml`:
   ```yaml
   name: CI

   on:
     push:
       branches: [main, develop]
     pull_request:
       branches: [main, develop]

   env:
     PYTHON_VERSION: "3.13"
     NODE_VERSION: "20"

   jobs:
     backend-lint:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: ${{ env.PYTHON_VERSION }}
         - name: Install dependencies
           run: |
             cd backend
             pip install -r requirements.txt -r requirements-dev.txt
         - name: Lint with ruff
           run: |
             cd backend
             ruff check .
             ruff format --check .

     backend-test:
       runs-on: ubuntu-latest
       services:
         postgres:
           image: postgres:18
           env:
             POSTGRES_USER: test
             POSTGRES_PASSWORD: test
             POSTGRES_DB: test
           ports:
             - 5432:5432
           options: >-
             --health-cmd pg_isready
             --health-interval 10s
             --health-timeout 5s
             --health-retries 5
         redis:
           image: redis:7
           ports:
             - 6379:6379
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: ${{ env.PYTHON_VERSION }}
         - name: Install dependencies
           run: |
             cd backend
             pip install -r requirements.txt -r requirements-dev.txt
         - name: Run tests
           env:
             DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test
             REDIS_URL: redis://localhost:6379/0
           run: |
             cd backend
             pytest --cov=app --cov-report=xml

     frontend-lint:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-node@v4
           with:
             node-version: ${{ env.NODE_VERSION }}
             cache: 'npm'
             cache-dependency-path: frontend/package-lock.json
         - name: Install dependencies
           run: |
             cd frontend
             npm ci
         - name: Lint
           run: |
             cd frontend
             npm run lint

     frontend-test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-node@v4
           with:
             node-version: ${{ env.NODE_VERSION }}
             cache: 'npm'
             cache-dependency-path: frontend/package-lock.json
         - name: Install dependencies
           run: |
             cd frontend
             npm ci
         - name: Test
           run: |
             cd frontend
             npm test -- --run
   ```

3. **Copy build workflow (`build.yml`):**

   Create `.github/workflows/build.yml`:
   ```yaml
   name: Build

   on:
     push:
       branches: [main]
     workflow_dispatch:

   env:
     REGISTRY: ghcr.io
     IMAGE_NAME_BACKEND: ${{ github.repository }}-backend
     IMAGE_NAME_FRONTEND: ${{ github.repository }}-frontend

   jobs:
     build-backend:
       runs-on: ubuntu-latest
       permissions:
         contents: read
         packages: write
       steps:
         - uses: actions/checkout@v4
         - uses: docker/login-action@v3
           with:
             registry: ${{ env.REGISTRY }}
             username: ${{ github.actor }}
             password: ${{ secrets.GITHUB_TOKEN }}
         - uses: docker/build-push-action@v5
           with:
             context: ./backend
             push: true
             tags: |
               ${{ env.REGISTRY }}/${{ env.IMAGE_NAME_BACKEND }}:latest
               ${{ env.REGISTRY }}/${{ env.IMAGE_NAME_BACKEND }}:${{ github.sha }}

     build-frontend:
       runs-on: ubuntu-latest
       permissions:
         contents: read
         packages: write
       steps:
         - uses: actions/checkout@v4
         - uses: docker/login-action@v3
           with:
             registry: ${{ env.REGISTRY }}
             username: ${{ github.actor }}
             password: ${{ secrets.GITHUB_TOKEN }}
         - uses: docker/build-push-action@v5
           with:
             context: ./frontend
             push: true
             tags: |
               ${{ env.REGISTRY }}/${{ env.IMAGE_NAME_FRONTEND }}:latest
               ${{ env.REGISTRY }}/${{ env.IMAGE_NAME_FRONTEND }}:${{ github.sha }}
   ```

4. **Copy Dependabot config:**

   Create `.github/dependabot.yml`:
   ```yaml
   version: 2
   updates:
     - package-ecosystem: "pip"
       directory: "/backend"
       schedule:
         interval: "weekly"
       open-pull-requests-limit: 5

     - package-ecosystem: "npm"
       directory: "/frontend"
       schedule:
         interval: "weekly"
       open-pull-requests-limit: 5

     - package-ecosystem: "docker"
       directory: "/"
       schedule:
         interval: "weekly"

     - package-ecosystem: "github-actions"
       directory: "/"
       schedule:
         interval: "weekly"
   ```

5. **Test workflows:**
   ```bash
   # Push to trigger CI
   git add .github/
   git commit -m "Add CI/CD workflows"
   git push origin feature/production-essentials-migration

   # Create PR to test CI workflow
   gh pr create --title "Add CI/CD Pipeline" --body "Adds GitHub Actions workflows"

   # View workflow runs
   gh run list
   ```

**Verification:**
- [ ] CI workflow runs on PR
- [ ] Build workflow runs on merge to main
- [ ] Dependabot creates dependency PRs

---

### Security Hardening

**Files to add/modify:**

| File | Action |
|------|--------|
| `backend/app/middleware/security.py` | Add |
| `backend/app/core/config.py` | Modify |
| `backend/app/main.py` | Modify |
| `.pre-commit-config.yaml` | Modify |
| `.gitleaks.toml` | Add |

**Steps:**

1. **Add security headers middleware:**

   Create `backend/app/middleware/security.py`:
   ```python
   """Security headers middleware for FastAPI."""
   from typing import Callable

   from starlette.middleware.base import BaseHTTPMiddleware
   from starlette.requests import Request
   from starlette.responses import Response

   from app.core.config import settings


   class SecurityHeadersMiddleware(BaseHTTPMiddleware):
       """Add security headers to all responses."""

       async def dispatch(
           self, request: Request, call_next: Callable
       ) -> Response:
           response = await call_next(request)

           # Always add these headers
           response.headers["X-Content-Type-Options"] = "nosniff"
           response.headers["X-Frame-Options"] = settings.X_FRAME_OPTIONS
           response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
           response.headers["X-XSS-Protection"] = "1; mode=block"

           # Add CSP if enabled
           if settings.CSP_ENABLED and settings.CSP_DIRECTIVES:
               response.headers["Content-Security-Policy"] = settings.CSP_DIRECTIVES

           # Add HSTS for HTTPS connections (or if forced)
           if settings.HSTS_ENABLED:
               if request.url.scheme == "https" or settings.FORCE_HSTS:
                   response.headers["Strict-Transport-Security"] = (
                       f"max-age={settings.HSTS_MAX_AGE}; includeSubDomains"
                   )

           return response
   ```

2. **Update `backend/app/core/config.py`:**

   Add to your Settings class:
   ```python
   # Security Headers
   SECURITY_HEADERS_ENABLED: bool = True
   X_FRAME_OPTIONS: str = "DENY"
   CONTENT_TYPE_OPTIONS: str = "nosniff"
   CSP_ENABLED: bool = True
   CSP_DIRECTIVES: str = (
       "default-src 'self'; "
       "script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: https:; "
       "font-src 'self'; "
       "connect-src 'self'"
   )
   HSTS_ENABLED: bool = True
   HSTS_MAX_AGE: int = 31536000  # 1 year
   FORCE_HSTS: bool = False
   ```

3. **Update `backend/app/main.py`:**

   Add after CORS middleware:
   ```python
   from app.middleware.security import SecurityHeadersMiddleware

   # After CORSMiddleware registration
   if settings.SECURITY_HEADERS_ENABLED:
       app.add_middleware(SecurityHeadersMiddleware)
   ```

4. **Update pre-commit config:**

   Add to `.pre-commit-config.yaml`:
   ```yaml
   - repo: https://github.com/gitleaks/gitleaks
     rev: v8.18.0
     hooks:
       - id: gitleaks
   ```

5. **Add Gitleaks configuration:**

   Create `.gitleaks.toml`:
   ```toml
   [extend]
   useDefault = true

   [allowlist]
   description = "Global allowlist"
   paths = [
     '''\.env\.example$''',
     '''\.env\..*\.example$''',
     '''tests/.*''',
     '''docs/.*''',
   ]
   ```

6. **Install updated hooks:**
   ```bash
   pre-commit install
   pre-commit run --all-files
   ```

**Verification:**
- [ ] Security headers appear in API responses:
  ```bash
  curl -I http://localhost:8000/health
  ```
- [ ] Pre-commit hooks run gitleaks
- [ ] No secrets detected in codebase

---

### Operational Readiness

**Files to add:**

| File | Action |
|------|--------|
| `scripts/db-backup.sh` | Add |
| `scripts/db-restore.sh` | Add |
| `scripts/db-verify.sh` | Add |
| `scripts/backup-config.env.example` | Add |
| `docs/runbooks/` | Add directory with runbooks |

**Steps:**

1. **Copy backup scripts from reference project:**
   ```bash
   # Copy from reference project
   cp /tmp/reference-project/scripts/db-backup.sh scripts/
   cp /tmp/reference-project/scripts/db-restore.sh scripts/
   cp /tmp/reference-project/scripts/db-verify.sh scripts/
   cp /tmp/reference-project/scripts/backup-config.env.example scripts/

   # Make executable
   chmod +x scripts/db-backup.sh scripts/db-restore.sh scripts/db-verify.sh
   ```

2. **Create backup directory:**
   ```bash
   mkdir -p backups
   echo "*.sql" >> backups/.gitignore
   echo "*.sql.gz" >> backups/.gitignore
   ```

3. **Copy runbooks:**
   ```bash
   mkdir -p docs/runbooks
   cp -r /tmp/reference-project/docs/runbooks/* docs/runbooks/
   ```

4. **Test backup and restore:**
   ```bash
   # Create a backup
   ./scripts/db-backup.sh

   # Verify the backup
   ./scripts/db-verify.sh backups/latest.sql.gz

   # Test restore (to temporary database)
   ./scripts/db-verify.sh backups/latest.sql.gz --test-restore
   ```

**Verification:**
- [ ] Backup script creates valid backups
- [ ] Restore script can restore from backup
- [ ] Verification script validates backup integrity

---

### Kubernetes Deployment

**Files to add:**
```
k8s/
  base/
    kustomization.yaml
    namespace.yaml
    configmap.yaml
    secret.yaml
    backend-deployment.yaml
    backend-service.yaml
    frontend-deployment.yaml
    frontend-service.yaml
    ingress.yaml
  overlays/
    staging/
      kustomization.yaml
      configmap-patch.yaml
      replicas-patch.yaml
      resources-patch.yaml
    production/
      kustomization.yaml
      configmap-patch.yaml
      replicas-patch.yaml
      resources-patch.yaml
      pdb.yaml
```

**Steps:**

1. **Create directory structure:**
   ```bash
   mkdir -p k8s/base k8s/overlays/staging k8s/overlays/production
   ```

2. **Copy base manifests:**
   ```bash
   cp /tmp/reference-project/k8s/base/* k8s/base/
   ```

3. **Copy overlay manifests:**
   ```bash
   cp /tmp/reference-project/k8s/overlays/staging/* k8s/overlays/staging/
   cp /tmp/reference-project/k8s/overlays/production/* k8s/overlays/production/
   ```

4. **Customize for your project:**

   Update `k8s/base/configmap.yaml` with your values:
   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: knowledge-mapper-config
   data:
     ENVIRONMENT: "production"
     LOG_LEVEL: "INFO"
     # Add your configuration values
   ```

   Update image references in deployments:
   ```yaml
   # In backend-deployment.yaml
   image: ghcr.io/YOUR_ORG/knowledge-mapper-backend:latest

   # In frontend-deployment.yaml
   image: ghcr.io/YOUR_ORG/knowledge-mapper-frontend:latest
   ```

   Update ingress hosts:
   ```yaml
   # In ingress.yaml
   spec:
     rules:
       - host: api.your-domain.com
         # ...
       - host: app.your-domain.com
         # ...
   ```

5. **Test manifests:**
   ```bash
   # Validate syntax
   kubectl kustomize k8s/overlays/staging

   # Dry run against cluster
   kubectl apply -k k8s/overlays/staging --dry-run=client -o yaml
   ```

**Verification:**
- [ ] Kustomize renders manifests without errors
- [ ] Manifests apply to a test cluster
- [ ] Services are reachable after deployment

---

### Developer Experience

**Files to add:**

| File | Action |
|------|--------|
| `frontend/openapitools.json` | Add |
| `frontend/.openapi-generator-ignore` | Add |
| `scripts/generate-api-client.sh` | Add |
| `scripts/load-test.sh` | Add |
| `tests/load/` | Add directory |

**Steps:**

1. **Add OpenAPI Generator config:**

   Create `frontend/openapitools.json`:
   ```json
   {
     "$schema": "node_modules/@openapitools/openapi-generator-cli/config.schema.json",
     "spaces": 2,
     "generator-cli": {
       "version": "7.0.0",
       "generators": {
         "typescript-fetch": {
           "generatorName": "typescript-fetch",
           "inputSpec": "http://localhost:8000/openapi.json",
           "output": "src/api/generated",
           "additionalProperties": {
             "supportsES6": true,
             "typescriptThreePlus": true,
             "withInterfaces": true
           }
         }
       }
     }
   }
   ```

2. **Add generator ignore file:**

   Create `frontend/.openapi-generator-ignore`:
   ```
   # Don't overwrite custom implementations
   src/api/generated/custom/**
   ```

3. **Add generation script:**
   ```bash
   cp /tmp/reference-project/scripts/generate-api-client.sh scripts/
   chmod +x scripts/generate-api-client.sh
   ```

4. **Install frontend dependencies:**
   ```bash
   cd frontend
   npm install --save-dev @openapitools/openapi-generator-cli
   ```

5. **Add npm script to `frontend/package.json`:**
   ```json
   {
     "scripts": {
       "generate:api": "openapi-generator-cli generate"
     }
   }
   ```

6. **Add k6 load tests:**
   ```bash
   mkdir -p tests/load
   cp -r /tmp/reference-project/tests/load/* tests/load/
   cp /tmp/reference-project/scripts/load-test.sh scripts/
   chmod +x scripts/load-test.sh
   ```

7. **Test generation:**
   ```bash
   # Start backend
   ./scripts/docker-dev.sh up

   # Validate OpenAPI spec
   ./scripts/generate-api-client.sh --validate

   # Generate client
   ./scripts/generate-api-client.sh
   ```

8. **Test load testing:**
   ```bash
   # Install k6 (if not already installed)
   # macOS: brew install k6
   # Linux: see https://k6.io/docs/getting-started/installation/

   # Run smoke test
   ./scripts/load-test.sh smoke
   ```

**Verification:**
- [ ] API client generates without errors
- [ ] k6 tests run successfully
- [ ] Generated client compiles with TypeScript

---

## Post-Migration Verification

Run this complete checklist after finishing all migrations:

### Core Functionality
- [ ] All existing tests pass: `cd backend && pytest`
- [ ] Application starts without errors: `./scripts/docker-dev.sh up`
- [ ] Authentication flow works (login with test users)
- [ ] Database operations work (CRUD operations)

### New Features

**CI/CD Pipeline:**
- [ ] CI workflow runs on PR
- [ ] Build workflow creates Docker images
- [ ] Images are pushed to GHCR

**Security:**
- [ ] Security headers present in responses:
  ```bash
  curl -I http://localhost:8000/health | grep -E "(X-Frame|X-Content|CSP|HSTS)"
  ```
- [ ] Gitleaks pre-commit hook runs

**Operations:**
- [ ] Backup script creates valid backup:
  ```bash
  ./scripts/db-backup.sh && ls -la backups/
  ```
- [ ] Restore script works:
  ```bash
  ./scripts/db-restore.sh --latest --dry-run
  ```

**Developer Experience:**
- [ ] API client generates:
  ```bash
  ./scripts/generate-api-client.sh
  ```
- [ ] Load tests run:
  ```bash
  ./scripts/load-test.sh smoke
  ```

### Integration
- [ ] Pre-commit hooks run without errors:
  ```bash
  pre-commit run --all-files
  ```
- [ ] Docker build completes:
  ```bash
  docker compose build
  ```
- [ ] Kubernetes manifests validate (if added):
  ```bash
  kubectl kustomize k8s/overlays/staging
  ```

---

## Troubleshooting

### CI Pipeline Issues

**Problem:** Workflow fails with "permission denied"
```bash
# Solution: Update repository settings
# Settings > Actions > General > Workflow permissions
# Select "Read and write permissions"

# For GHCR push issues
# Settings > Actions > General > Workflow permissions
# Check "Allow GitHub Actions to create and approve pull requests"
```

**Problem:** Tests fail in CI but pass locally
```bash
# Check for environment differences
# 1. Verify Python/Node versions match
python --version
node --version

# 2. Check for hardcoded localhost references
grep -r "localhost" tests/

# 3. Ensure environment variables are set in CI
# Check workflow file for env: section
```

### Security Headers Issues

**Problem:** CSP blocks legitimate resources
```bash
# Check current headers
curl -I http://localhost:8000/health

# Update CSP_DIRECTIVES in .env
CSP_DIRECTIVES="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.example.com"
```

**Problem:** HSTS causes issues in development
```bash
# Disable HSTS for development
# In .env:
HSTS_ENABLED=false

# Or only enable for production
FORCE_HSTS=false  # Only adds HSTS header for HTTPS requests
```

### Backup/Restore Issues

**Problem:** Backup script fails with Docker errors
```bash
# Check Docker is running
docker ps

# Verify container name
docker compose ps

# Check backup directory permissions
ls -la backups/
chmod 755 backups/
```

**Problem:** Restore fails with permission errors
```bash
# Ensure script is executable
chmod +x scripts/db-restore.sh

# Run with debug
BACKUP_DEBUG=true ./scripts/db-restore.sh --latest
```

### Kubernetes Issues

**Problem:** ImagePullBackOff
```bash
# Check if image exists
docker pull ghcr.io/your-org/knowledge-mapper-backend:latest

# Verify image pull secrets
kubectl get secret regcred -n knowledge-mapper -o yaml

# Create image pull secret if missing
kubectl create secret docker-registry regcred \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_GITHUB_TOKEN \
  -n knowledge-mapper
```

**Problem:** ConfigMap not updating in pods
```bash
# Force pod restart
kubectl rollout restart deployment/backend -n knowledge-mapper

# Watch rollout
kubectl rollout status deployment/backend -n knowledge-mapper
```

### API Client Generation Issues

**Problem:** Cannot connect to OpenAPI spec
```bash
# Verify backend is running
curl http://localhost:8000/openapi.json

# Start backend if needed
./scripts/docker-dev.sh up backend
```

**Problem:** Generated code has TypeScript errors
```bash
# Regenerate with clean output
rm -rf frontend/src/api/generated
./scripts/generate-api-client.sh

# Check OpenAPI spec for issues
./scripts/generate-api-client.sh --validate
```

---

## Rollback Procedures

### Complete Rollback (Git)

```bash
# Option 1: Revert to backup branch
git checkout pre-migration-backup
git checkout -b main-rollback
git push origin main-rollback

# Option 2: Hard reset main (destructive)
git checkout main
git reset --hard pre-migration-backup
git push --force-with-lease origin main
```

### Partial Rollback

To remove specific features without full rollback:

**Remove CI/CD:**
```bash
rm -rf .github/workflows
rm .github/dependabot.yml
git add -A && git commit -m "Remove CI/CD workflows"
```

**Remove Security Headers:**
```bash
rm backend/app/middleware/security.py

# Revert config.py changes (remove security settings)
# Revert main.py changes (remove middleware registration)

# Or use git to restore original files
git checkout pre-migration-backup -- backend/app/core/config.py
git checkout pre-migration-backup -- backend/app/main.py
```

**Remove Kubernetes:**
```bash
rm -rf k8s/
git add -A && git commit -m "Remove Kubernetes manifests"
```

**Remove Load Testing:**
```bash
rm -rf tests/load/
rm scripts/load-test.sh
git add -A && git commit -m "Remove load testing"
```

**Remove API Client Generation:**
```bash
rm frontend/openapitools.json
rm frontend/.openapi-generator-ignore
rm scripts/generate-api-client.sh
rm -rf frontend/src/api/generated
git add -A && git commit -m "Remove API client generation"
```

---

## Getting Help

If you encounter issues during migration:

1. **Check documentation:**
   - `CLAUDE.md` - Quick reference for all features
   - `docs/runbooks/` - Operational runbooks
   - `docs/operations/` - Detailed configuration guides

2. **Review Architecture Decision Records:**
   - `docs/decisions/` - ADRs explaining design rationale

3. **Open an issue:**
   - Template repository: GitHub Issues
   - Include: steps to reproduce, error messages, environment details

4. **Community resources:**
   - Project Discussions on GitHub
   - Stack Overflow (tag: `knowledge-mapper`)

---

*Last updated: Knowledge Mapper Template v2.0.0*

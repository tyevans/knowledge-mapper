# CI/CD Pipeline

This document describes the Continuous Integration and Continuous Deployment setup for Knowledge Mapper.


## GitHub Actions Workflows

### CI Workflow (`.github/workflows/ci.yml`)

The CI workflow runs on:
- Pull requests to `main` and `develop` branches
- Pushes to `main` branch

**Jobs:**

| Job | Description |
|-----|-------------|
| `backend-lint` | Ruff linting and format checking |
| `backend-test` | Pytest with PostgreSQL and Redis service containers |
| `frontend-lint` | ESLint |
| `frontend-test` | Vitest with coverage |

All jobs run in parallel to minimize CI time.

### Build Workflow (`.github/workflows/build.yml`)

The Build workflow runs on:
- Pushes to `main` branch
- Version tags (`v*`)
- Manual trigger (workflow_dispatch)

**Features:**
- Multi-platform builds (linux/amd64, linux/arm64)
- Docker layer caching via GitHub Actions cache
- SBOM generation for security scanning
- OCI-compliant image labels

**Images pushed to:**
- `ghcr.io/your-github-username/knowledge-mapper-backend`
- `ghcr.io/your-github-username/knowledge-mapper-frontend`

### Deploy Workflow (`.github/workflows/deploy.yml`)

The Deploy workflow handles Kubernetes deployments:

**Triggers:**
- Automatic staging deployment after successful Build on `main`
- Production deployment on version tags (`v*`)
- Manual deployment via workflow_dispatch

**Environments:**

| Environment | Trigger | Approval Required |
|-------------|---------|-------------------|
| `staging` | Build success on `main` | No (auto-deploy) |
| `production` | Version tag or manual | Yes (via GitHub Environment) |

**Features:**
- Kustomize-based image tag updates
- Deployment verification with health checks
- Rollback documentation in workflow summary
- Deployment status reporting to GitHub

For detailed deployment instructions, see the [Deployment Guide](../DEPLOYMENT.md).

## Coverage Reporting with Codecov

Test coverage is automatically uploaded to [Codecov](https://codecov.io) after each CI run.

### Coverage Thresholds

| Component | Target | Threshold |
|-----------|--------|-----------|
| Backend (Python) | 80% | 2% |
| Frontend (TypeScript) | 70% | 2% |
| Patch (new code) | 80% | 5% |

### Coverage Flags

Coverage is tracked separately for backend and frontend using Codecov flags:
- `backend` - Python/FastAPI coverage
- `frontend` - Lit/TypeScript coverage

### Setup Instructions

1. **Sign up for Codecov**
   - Go to [codecov.io](https://codecov.io)
   - Sign in with your GitHub account
   - Free for public repositories

2. **Add your repository**
   - Navigate to your Codecov dashboard
   - Click "Add new repository"
   - Select `your-github-username/knowledge-mapper`

3. **Get your upload token**
   - Go to your repository settings in Codecov
   - Copy the "Repository Upload Token"

4. **Add token to GitHub secrets**
   - Go to your GitHub repository
   - Navigate to Settings > Secrets and variables > Actions
   - Click "New repository secret"
   - Name: `CODECOV_TOKEN`
   - Value: (paste your token)

5. **Verify integration**
   - Push a commit or open a pull request
   - Check the Actions tab for successful coverage upload
   - Visit your Codecov dashboard to see coverage reports

### PR Comments

Codecov automatically adds coverage comments to pull requests showing:
- Coverage diff (lines added/removed)
- Impact on overall coverage
- Per-file coverage changes
- Coverage flags breakdown

### Configuration

The Codecov configuration is in `codecov.yml` at the project root. Key settings:

```yaml
coverage:
  status:
    project:
      backend:
        paths:
          - "backend/"
        target: 80%
      frontend:
        paths:
          - "frontend/"
        target: 70%
```

### Troubleshooting

**Coverage not uploading:**
1. Verify `CODECOV_TOKEN` is set in GitHub secrets
2. Check the CI workflow logs for Codecov action errors
3. Ensure coverage files are generated (`coverage.xml` for backend, `coverage/` for frontend)

**Badge not showing:**
- Ensure the repository is public OR the Codecov token has access
- Check badge URL matches your repository path

**Coverage lower than expected:**
- Review the `ignore` section in `codecov.yml`
- Ensure tests are running with coverage enabled
- Check if test files are being excluded properly


## Local Coverage

### Backend

```bash
cd backend
uv run pytest --cov=app --cov-report=html --cov-report=term
# Open htmlcov/index.html in browser
```

### Frontend

```bash
cd frontend
npm run test:coverage
# Coverage report in coverage/index.html
```

## Best Practices

1. **Write tests for new code** - Patch coverage target is 80%
2. **Don't ignore coverage drops** - Address them before merging
3. **Use coverage reports** - Identify untested code paths
4. **Test edge cases** - Coverage percentage != test quality

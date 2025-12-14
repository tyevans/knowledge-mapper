# ADR-022: Container Security Scanning

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2025-12-06 |
| **Decision Makers** | Project Team |
| **Related ADRs** | ADR-019 (GitHub Actions CI/CD), ADR-021 (Kubernetes Deployment) |

## Context

Container images are a critical part of the deployment pipeline. They bundle application code with operating system packages and runtime dependencies, creating a large attack surface. Known vulnerabilities (CVEs) in these components can expose applications to:

- Remote code execution
- Privilege escalation
- Data exfiltration
- Denial of service

The template needs automated vulnerability scanning to:

1. **Prevent deployment of images with known critical vulnerabilities**
2. **Provide visibility into the security posture of deployed containers**
3. **Enable proactive remediation before vulnerabilities are exploited**
4. **Support compliance requirements** (SOC2, PCI-DSS, HIPAA, etc.)

### Scanning Requirements

| Requirement | Description |
|-------------|-------------|
| Pre-merge Scanning | Block PRs that introduce critical vulnerabilities |
| Main Branch Scanning | Scan images after successful build |
| Scheduled Scanning | Detect newly disclosed CVEs in existing images |
| SBOM Integration | Support software bill of materials for supply chain security |
| SARIF Integration | Upload results to GitHub Security tab |

## Decision

We adopt **Trivy** by Aqua Security as our container security scanner, integrated into GitHub Actions via the official `aquasecurity/trivy-action`.

### Why Trivy

| Factor | Trivy | Snyk | Grype | Clair |
|--------|-------|------|-------|-------|
| Cost | Free/OSS | Freemium | Free/OSS | Free/OSS |
| GitHub Action | Official | Official | Community | None |
| Scan Speed | Fast (~1-2 min) | Medium (~3-5 min) | Fast (~1-2 min) | Slow (~5-10 min) |
| SARIF Output | Yes | Yes | Yes | No |
| SBOM Support | Yes (CycloneDX, SPDX) | Limited | Yes | No |
| Offline Mode | Yes | No | Yes | Yes |
| DB Updates | Automatic | Managed | Automatic | Manual |
| Language Support | Comprehensive | Comprehensive | Good | Limited |
| IaC Scanning | Yes | Yes | No | No |
| License Scanning | Yes | Yes | No | No |

### Scanning Strategy

The security workflow implements a multi-layered scanning approach:

#### 1. Pull Request Scanning

```yaml
on:
  pull_request:
    branches: [main, develop]
```

- Build image locally (not pushed to registry)
- Scan with Trivy before merge
- **Fail on HIGH or CRITICAL severity**
- Upload SARIF to GitHub Security tab
- Generate human-readable artifact for review

#### 2. Main Branch Scanning

```yaml
on:
  push:
    branches: [main]
```

- Scan after successful image build
- Results inform release decisions
- SARIF provides audit trail
- Artifacts retained for 30 days

#### 3. Scheduled Scanning (Weekly)

```yaml
on:
  schedule:
    - cron: '0 6 * * 1'  # Monday at 6 AM UTC
```

- Detect newly disclosed CVEs
- Alert team to new findings in existing images
- Catch vulnerabilities published after initial deployment

### Severity Handling

| Severity | Exit Code | Workflow Result | Action Required |
|----------|-----------|-----------------|-----------------|
| CRITICAL | 1 | Fail | Block merge, immediate attention |
| HIGH | 1 | Fail | Block merge, fix before release |
| MEDIUM | 0 | Pass | Report only, track in backlog |
| LOW | 0 | Pass | Report only, informational |

### Unfixed Vulnerabilities

```yaml
ignore-unfixed: true
```

Vulnerabilities without available patches do not fail the build because:

- Prevents blocking on issues developers cannot fix
- Still reported for visibility and tracking
- Can be overridden per-repository if stricter policy needed
- Teams should monitor for patch availability

### Scan Types

The workflow includes multiple scan types:

| Scan Type | Target | Purpose |
|-----------|--------|---------|
| Container Image | Built Docker images | OS packages, application dependencies |
| Filesystem | Repository source code | IaC misconfigurations, embedded secrets |

### Output Formats

| Format | Purpose | Integration |
|--------|---------|-------------|
| SARIF | GitHub Security tab integration | Code scanning alerts, PR annotations |
| Table | Human-readable artifact | Manual review, debugging |
| JSON | Machine-readable (optional) | Automation, metrics collection |

### Ignore File (.trivyignore)

False positives and accepted risks are managed via `.trivyignore`:

```
# .trivyignore
# Format: CVE-ID or vulnerability ID, one per line
# Only ignore after security team review

# CVE-YYYY-NNNNN - Reason for ignoring, reviewed by @reviewer on YYYY-MM-DD
# Example: Not exploitable in our configuration (no network exposure)
```

Guidelines for using .trivyignore:

1. **Document the reason** for each ignored vulnerability
2. **Require security review** before adding entries
3. **Set expiration dates** to revisit decisions periodically
4. **Prefer patching** over ignoring when possible

## Consequences

### Positive

1. **Shift-Left Security**: Vulnerabilities caught before deployment, reducing remediation cost

2. **Automated Enforcement**: No manual security review for common CVEs; consistent policy application

3. **Visibility**: GitHub Security tab provides centralized view of vulnerabilities across repositories

4. **Compliance Support**: SARIF reports provide audit trail for SOC2, PCI-DSS, and similar frameworks

5. **Free Tooling**: No additional cost for open source projects; Apache 2.0 license

6. **Fast Feedback**: Scans complete in 1-3 minutes with caching; minimal CI overhead

7. **Comprehensive Coverage**: Scans OS packages, language dependencies, and misconfigurations

8. **GitHub Native Integration**: Results appear in Security tab and PR annotations

### Negative

1. **False Positives**: Some reported vulnerabilities may not be exploitable in context
   - Mitigation: Use .trivyignore with documented justification

2. **Database Lag**: New CVEs take 12-48 hours to appear in Trivy DB
   - Mitigation: Schedule scans catch delayed entries

3. **Build Time**: Adds 2-3 minutes to CI pipeline
   - Mitigation: Trivy DB caching reduces scan time

4. **Ignore File Maintenance**: `.trivyignore` requires ongoing review and cleanup
   - Mitigation: Regular security review cadence

5. **Context-Free Scanning**: Cannot assess exploitability in production environment
   - Mitigation: Combine with runtime security monitoring

### Neutral

1. **Database Updates**: Trivy DB updates automatically but requires internet access during CI

2. **Multi-Platform Images**: Each architecture (amd64, arm64) requires separate scanning

3. **Runtime Security Gap**: This decision addresses build-time scanning only; runtime security (admission controllers, runtime protection) requires separate tooling

---

## Alternatives Considered

### 1. Snyk Container

**Approach**: Use Snyk for container and dependency scanning.

```yaml
- uses: snyk/actions/docker@master
  with:
    image: myimage:tag
    args: --severity-threshold=high
```

**Strengths**:
- Excellent developer experience and UI
- Detailed remediation advice with fix PRs
- Enterprise features (policies, reporting)
- Broad language and framework support

**Why Not Chosen**:
- Freemium model limits free tier usage (100 tests/month)
- Full features require paid subscription
- Slower scan times than Trivy
- Trivy sufficient for template needs

**When to Reconsider**:
- Enterprise requiring advanced policy controls
- Need for automated remediation PRs
- Existing Snyk subscription

### 2. Grype (Anchore)

**Approach**: Use Anchore Grype for SBOM-first vulnerability scanning.

```yaml
- uses: anchore/scan-action@v4
  with:
    image: myimage:tag
    fail-build: true
    severity-cutoff: high
```

**Strengths**:
- Fast scanning with low memory usage
- SBOM-native approach (Syft integration)
- Strong accuracy for OS packages
- Active open-source development

**Why Not Chosen**:
- GitHub Action is community-maintained (not official)
- Smaller community than Trivy
- Less mature documentation
- Trivy has broader feature set (IaC, secrets)

**When to Reconsider**:
- SBOM-first security program
- Already using Anchore Enterprise

### 3. Clair (Quay)

**Approach**: Use Clair for container vulnerability scanning.

**Strengths**:
- Mature project, battle-tested at scale
- Used by Quay.io container registry
- PostgreSQL backend for large deployments

**Why Not Chosen**:
- Complex setup (requires database, server deployment)
- No official GitHub Action available
- No SARIF output format
- Designed for registry-side scanning, not CI
- Less active development

### 4. GitHub Native (Dependabot + CodeQL)

**Approach**: Rely on GitHub's built-in security features only.

**Strengths**:
- No additional tooling configuration
- Native integration with repository
- Automatic PR creation for updates

**Why Not Chosen**:
- Dependabot: dependency updates only, not container scanning
- CodeQL: code analysis, not vulnerability database scanning
- Neither provides comprehensive container image scanning
- Missing OS package vulnerability detection

---

## Implementation Details

### Workflow Configuration

```yaml
# .github/workflows/security.yml
trivy-image-scan:
  name: Container Image Scan
  runs-on: ubuntu-latest
  strategy:
    matrix:
      include:
        - service: backend
          dockerfile: backend/Dockerfile
        - service: frontend
          dockerfile: frontend/Dockerfile
  steps:
    - name: Run Trivy vulnerability scanner
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: ${{ matrix.service }}:scan
        format: 'sarif'
        output: 'trivy-${{ matrix.service }}.sarif'
        severity: 'CRITICAL,HIGH,MEDIUM'
        exit-code: '1'
        ignore-unfixed: true
        vuln-type: 'os,library'
        trivyignores: '.trivyignore'

    - name: Upload Trivy scan results
      uses: github/codeql-action/upload-sarif@v3
      if: always()
      with:
        sarif_file: 'trivy-${{ matrix.service }}.sarif'
```

### Trivy DB Caching

```yaml
- name: Cache Trivy DB
  uses: actions/cache@v4
  with:
    path: ~/.cache/trivy
    key: trivy-db-${{ github.run_id }}
    restore-keys: |
      trivy-db-
```

Caching reduces scan time from ~2 minutes to ~30 seconds for repeated scans.

### Filesystem Scanning

In addition to container images, Trivy scans the repository filesystem:

```yaml
- uses: aquasecurity/trivy-action@master
  with:
    scan-type: 'fs'
    scan-ref: '.'
    severity: 'CRITICAL,HIGH'
```

This catches:
- Hardcoded secrets in configuration
- IaC misconfigurations (Terraform, CloudFormation)
- Vulnerable dependencies in lock files

---

## Related ADRs

- [ADR-019: GitHub Actions CI/CD](./ADR-019-github-actions-cicd.md) - Workflow infrastructure
- [ADR-020: Security Headers](./ADR-020-security-headers.md) - Application-level security
- [ADR-021: Kubernetes Deployment](./ADR-021-kubernetes-deployment.md) - Deployment target for scanned images

## Implementation References

- `.github/workflows/security.yml` - Security scanning workflow
- `.trivyignore` - Vulnerability ignore list
- `backend/Dockerfile` - Backend container image
- `frontend/Dockerfile` - Frontend container image

## External References

- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [Trivy GitHub Action](https://github.com/aquasecurity/trivy-action)
- [SARIF Specification](https://sarifweb.azurewebsites.net/)
- [GitHub Code Scanning](https://docs.github.com/en/code-security/code-scanning)
- [CVE Database](https://cve.mitre.org/)
- [NVD (National Vulnerability Database)](https://nvd.nist.gov/)
- [OWASP Container Security](https://owasp.org/www-project-docker-security/)

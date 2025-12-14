# Secrets Management Guide

This document describes how to handle secrets and sensitive data in Knowledge Mapper.

## Pre-commit Hook

This project uses [gitleaks](https://github.com/gitleaks/gitleaks) to detect secrets before they are committed.

### Setup

1. Install pre-commit:
   ```bash
   pip install pre-commit
   # or
   uv add --dev pre-commit
   ```

2. Install the hooks:
   ```bash
   pre-commit install
   ```

3. Test the setup:
   ```bash
   pre-commit run --all-files
   ```

### What Gets Detected

Gitleaks detects:
- API keys (AWS, GCP, Azure, etc.)
- Private keys (RSA, DSA, EC, etc.)
- Database connection strings with passwords
- JWT tokens and secrets
- OAuth client secrets
- Generic high-entropy strings that look like secrets

### Handling False Positives

If gitleaks flags a legitimate non-secret (e.g., a test fixture):

1. **Verify it's not a real secret** - double-check the flagged content

2. **Add to allowlist** - edit `.gitleaks.toml`:
   ```toml
   [allowlist]
   paths = [
       '''path/to/file\.txt''',
   ]
   ```

3. **Use regex patterns** - for specific patterns that are not secrets:
   ```toml
   [allowlist]
   regexes = [
       '''my-specific-pattern''',
   ]
   ```

4. **Use stopwords** - if the value contains indicator words like "example" or "test"

5. **Commit the allowlist change** - include justification in commit message

### If You Accidentally Commit a Secret

1. **Do NOT push** - if you haven't pushed yet, amend the commit:
   ```bash
   git reset --soft HEAD~1
   # Remove the secret from the file
   git add .
   git commit -m "Your message"
   ```

2. **Rotate the secret immediately** - assume it's compromised

3. **Remove from history** - use `git filter-branch` or BFG Repo-Cleaner:
   ```bash
   # Using BFG (recommended - faster and simpler)
   bfg --delete-files 'secret-file.txt'
   bfg --replace-text passwords.txt

   # Using git filter-branch
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch path/to/secret-file" \
     --prune-empty --tag-name-filter cat -- --all
   ```

4. **Force push** - after cleaning history (coordinate with team):
   ```bash
   git push --force
   ```

5. **Document the incident** - follow security incident procedures

### Scanning Modes

| Mode | Command | Use Case |
|------|---------|----------|
| protect | `gitleaks protect --staged` | Pre-commit hook (staged files only) |
| detect | `gitleaks detect` | CI/full repository scan |

### Manual Scanning

Run a full repository scan locally:
```bash
# Scan current state
gitleaks detect --source . --verbose

# Scan with report output
gitleaks detect --source . --report-path=leaks.json

# Scan specific commit range
gitleaks detect --source . --log-opts="HEAD~10..HEAD"
```

## Environment Variables

Use environment variables for all secrets:

```bash
# Never commit real values - BAD
DATABASE_URL=postgresql://user:realpassword@localhost/db

# Use environment variables - GOOD
DATABASE_URL=${DATABASE_URL}
```

See `.env.example` for the template of required environment variables.

### Environment File Rules

| File | Committed | Contains |
|------|-----------|----------|
| `.env.example` | Yes | Placeholder values, documentation |
| `.env` | No (gitignored) | Real secrets for local development |
| `.env.production` | No | Production secrets (use secret manager) |

## CI/CD Secrets

Store secrets in GitHub repository settings:
- Settings > Secrets and variables > Actions

### Required Secrets for Deployment

| Secret | Purpose |
|--------|---------|
| `REGISTRY_TOKEN` | Container registry authentication |
| `KUBECONFIG` | Kubernetes deployment credentials |
| `SENTRY_DSN` | Error tracking (if using Sentry) |

### Best Practices for CI/CD Secrets

1. **Use environment-specific secrets** - separate dev/staging/production
2. **Rotate regularly** - at least quarterly for sensitive credentials
3. **Audit access** - review who has access to repository secrets
4. **Use OIDC where possible** - avoid long-lived credentials

## Secret Management Solutions

For production environments, consider using a dedicated secret manager:

| Solution | Best For |
|----------|----------|
| AWS Secrets Manager | AWS-native applications |
| HashiCorp Vault | Multi-cloud, self-hosted |
| Azure Key Vault | Azure-native applications |
| Google Secret Manager | GCP-native applications |
| 1Password/Doppler | Developer-friendly, team secrets |

## Related Documentation

- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [gitleaks Documentation](https://github.com/gitleaks/gitleaks)
- [pre-commit Documentation](https://pre-commit.com/)
- [BFG Repo-Cleaner](https://rtyley.github.io/bfg-repo-cleaner/)

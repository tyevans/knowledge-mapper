# Configuration Validation and Troubleshooting Guide

This guide covers how to validate your Knowledge Mapper configuration and troubleshoot common configuration issues.

## Configuration Validation

### Automatic Validation at Startup

The application validates configuration automatically when it starts. Pydantic-settings performs:

1. **Type validation** - Ensures values match expected types (string, int, bool, list)
2. **Required field checks** - Verifies required environment variables are set
3. **Type coercion** - Converts strings to appropriate types (e.g., `"true"` -> `True`)

### Manual Configuration Validation

#### Backend Configuration Check

```bash
# In the backend container or virtual environment
cd backend

# Validate configuration loads without errors
python -c "from app.core.config import settings; print('Configuration valid')"

# Print all configuration (WARNING: may include secrets in output)
python -c "from app.core.config import settings; import json; print(json.dumps(settings.model_dump(), indent=2, default=str))"
```

#### Environment File Syntax Check

```bash
# Check for syntax errors in environment files
bash -n .env
bash -n .env.production.example
bash -n .env.staging.example
```

#### Required Variables Check

```bash
# Script to check required variables are set
#!/bin/bash
REQUIRED_VARS="DATABASE_URL MIGRATION_DATABASE_URL REDIS_URL OAUTH_ISSUER_URL"

for var in $REQUIRED_VARS; do
    if [ -z "${!var}" ]; then
        echo "ERROR: $var is not set"
        exit 1
    fi
done
echo "All required variables are set"
```

---

## Pre-Deployment Checklist

### Environment Configuration

| Check | Command/Action | Expected Result |
|-------|----------------|-----------------|
| Environment file exists | `ls -la .env` | File exists |
| Required vars set | Check script above | All vars present |
| No placeholder values | `grep -E 'CHANGE_ME\|TODO\|REPLACE' .env` | No matches |
| Debug disabled | `grep '^DEBUG=' .env` | `DEBUG=false` |
| Log level appropriate | `grep '^LOG_LEVEL=' .env` | `LOG_LEVEL=info` |

### Database Connectivity

```bash
# Test database connection
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def test():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        result = await conn.execute('SELECT 1')
        print('Database connection: OK')

asyncio.run(test())
"
```

### Redis Connectivity

```bash
# Test Redis connection
python -c "
import asyncio
import redis.asyncio as redis
from app.core.config import settings

async def test():
    r = redis.from_url(settings.REDIS_URL)
    await r.ping()
    print('Redis connection: OK')
    await r.close()

asyncio.run(test())
"
```

### OAuth/OIDC Configuration

```bash
# Test OIDC discovery endpoint
curl -s "${OAUTH_ISSUER_URL}/.well-known/openid-configuration" | jq .

# Verify JWKS endpoint is accessible
JWKS_URI=$(curl -s "${OAUTH_ISSUER_URL}/.well-known/openid-configuration" | jq -r .jwks_uri)
curl -s "$JWKS_URI" | jq .
```

---

## Common Issues and Solutions

### Database Connection Issues

#### Issue: `connection refused`

**Symptoms:**
```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection refused
```

**Causes and Solutions:**

| Cause | Solution |
|-------|----------|
| Database not running | Start the database: `docker compose up postgres -d` |
| Wrong hostname | Verify `DATABASE_URL` hostname matches container/service name |
| Wrong port | Check port mapping in `compose.yml` |
| Firewall blocking | Check network policies and security groups |

**Diagnostic commands:**
```bash
# Check if database is running
docker compose ps postgres

# Test network connectivity
nc -zv <db-host> 5432

# Test DNS resolution
nslookup <db-host>
```

#### Issue: `authentication failed`

**Symptoms:**
```
FATAL: password authentication failed for user "appuser"
```

**Solutions:**

1. Verify username in `DATABASE_URL` matches database user
2. Verify password is correct (check for special characters that need URL encoding)
3. Check if user exists: `psql -U postgres -c "\du"`
4. Verify user has permissions: `psql -U postgres -c "\l"`

**URL encoding for special characters:**
```bash
# Common characters that need encoding in URLs
# ! -> %21
# @ -> %40
# # -> %23
# $ -> %24
# % -> %25
# & -> %26
# = -> %3D
# + -> %2B
# / -> %2F

# Example: password "p@ss!word" becomes "p%40ss%21word"
DATABASE_URL=postgresql+asyncpg://user:p%40ss%21word@host:5432/db
```

#### Issue: `database does not exist`

**Symptoms:**
```
FATAL: database "myapp_db" does not exist
```

**Solutions:**
```bash
# Create the database
docker compose exec postgres psql -U postgres -c "CREATE DATABASE myapp_db;"

# Or apply migrations which may create it
alembic upgrade head
```

---

### Redis Connection Issues

#### Issue: `NOAUTH Authentication required`

**Symptoms:**
```
redis.exceptions.AuthenticationError: NOAUTH Authentication required
```

**Solutions:**

1. Add password to `REDIS_URL`: `redis://default:password@host:6379/0`
2. Verify password matches Redis configuration
3. Check Redis was started with password: `redis-cli AUTH password`

#### Issue: `Connection refused`

**Symptoms:**
```
redis.exceptions.ConnectionError: Error 111 connecting to redis:6379. Connection refused
```

**Solutions:**
```bash
# Check Redis is running
docker compose ps redis

# Test connectivity
redis-cli -h <redis-host> -p 6379 -a <password> ping
```

---

### OAuth/OIDC Issues

#### Issue: `Unable to fetch JWKS`

**Symptoms:**
```
JWKSFetchError: Unable to fetch JWKS from issuer
```

**Causes and Solutions:**

| Cause | Solution |
|-------|----------|
| Network connectivity | Ensure backend can reach Keycloak |
| Wrong issuer URL | Verify `OAUTH_ISSUER_URL` is correct |
| TLS certificate issues | Check certificate validity or add CA |
| DNS resolution | Verify DNS resolves correctly |

**Diagnostic commands:**
```bash
# Test from backend container
docker compose exec backend curl -v "${OAUTH_ISSUER_URL}/.well-known/openid-configuration"

# Check DNS resolution
docker compose exec backend nslookup keycloak
```

#### Issue: `Invalid token audience`

**Symptoms:**
```
InvalidAudienceError: Token audience does not match expected value
```

**Solutions:**

1. Verify `OAUTH_AUDIENCE` matches the `aud` claim in tokens
2. Check Keycloak client configuration for audience mapping
3. Decode a token to inspect claims:

```bash
# Decode JWT (without verification) to inspect claims
echo "<token>" | cut -d'.' -f2 | base64 -d | jq .
```

#### Issue: Token validation fails after key rotation

**Symptoms:**
```
InvalidSignatureError: Token signature validation failed
```

**Solutions:**

1. Clear JWKS cache by restarting the application
2. Reduce `JWKS_CACHE_TTL` for faster key rotation pickup
3. Verify Keycloak has the correct signing key active

---

### CORS Issues

#### Issue: `CORS policy: No 'Access-Control-Allow-Origin'`

**Symptoms:**
Browser console shows:
```
Access to fetch at 'https://api.example.com' from origin 'https://app.example.com'
has been blocked by CORS policy
```

**Solutions:**

1. Add frontend origin to `CORS_ORIGINS`:
   ```bash
   CORS_ORIGINS=https://app.example.com,https://www.example.com
   ```

2. For development, temporarily allow all:
   ```bash
   CORS_ORIGINS=*
   ```
   **Warning:** Never use `*` in production.

3. Verify the origin matches exactly (protocol, domain, port):
   - `http://localhost:3000` != `http://localhost`
   - `https://example.com` != `https://www.example.com`

---

### Rate Limiting Issues

#### Issue: `429 Too Many Requests`

**Symptoms:**
```
HTTP 429: Rate limit exceeded
```

**Solutions:**

1. Increase limits (if appropriate):
   ```bash
   RATE_LIMIT_REQUESTS_PER_MINUTE=200
   RATE_LIMIT_FAILED_AUTH_PER_MINUTE=20
   ```

2. For load testing, temporarily disable:
   ```bash
   RATE_LIMIT_ENABLED=false
   ```
   **Warning:** Never disable in production.

3. Check Redis is accessible (rate limits stored in Redis)

---

### Security Header Issues

#### Issue: Resources blocked by CSP

**Symptoms:**
Browser console shows:
```
Refused to load the script 'https://cdn.example.com/script.js' because it
violates the Content-Security-Policy directive
```

**Solutions:**

1. Add the source to the appropriate CSP directive:
   ```bash
   CSP_SCRIPT_SRC="'self' 'unsafe-inline' https://cdn.example.com"
   ```

2. For development, disable CSP temporarily:
   ```bash
   CSP_ENABLED=false
   ```
   **Warning:** Re-enable before production deployment.

---

## Kubernetes-Specific Troubleshooting

### ConfigMap Not Applied

```bash
# Check ConfigMap exists
kubectl get configmap knowledge-mapper-config -n knowledge-mapper

# View ConfigMap contents
kubectl describe configmap knowledge-mapper-config -n knowledge-mapper

# Check pod is using ConfigMap
kubectl get pod <pod-name> -n knowledge-mapper -o yaml | grep -A 10 envFrom
```

### Secret Not Mounted

```bash
# Check Secret exists
kubectl get secret knowledge-mapper-secrets -n knowledge-mapper

# Check pod can access secret
kubectl exec -n knowledge-mapper <pod-name> -- env | grep DATABASE

# Check for permission issues
kubectl auth can-i get secrets --as=system:serviceaccount:knowledge-mapper:default
```

### Environment Variables in Pod

```bash
# List all environment variables in pod
kubectl exec -n knowledge-mapper <pod-name> -- env | sort

# Check specific variable
kubectl exec -n knowledge-mapper <pod-name> -- printenv DATABASE_URL
```

---

## Debugging Configuration

### Enable Debug Logging

```bash
# Temporarily enable debug mode
DEBUG=true
LOG_LEVEL=debug

# Restart the application
docker compose restart backend
# or
kubectl rollout restart deployment/backend -n knowledge-mapper
```

### Print Configuration at Startup

Add to application startup for debugging:

```python
# In main.py or startup
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

# Print non-sensitive settings
logger.info(f"Environment: {settings.ENV}")
logger.info(f"Debug: {settings.DEBUG}")
logger.info(f"API Prefix: {settings.API_V1_PREFIX}")
logger.info(f"OAuth Issuer: {settings.OAUTH_ISSUER_URL}")

# Never log secrets!
# logger.info(f"Database: {settings.DATABASE_URL}")  # DON'T DO THIS
```

### Configuration Dump Script

Create a safe configuration dump:

```python
#!/usr/bin/env python
"""Dump configuration (without secrets) for debugging."""

from app.core.config import settings
import json

# Fields that should never be printed
SECRETS = {'DATABASE_URL', 'MIGRATION_DATABASE_URL', 'REDIS_URL',
           'OAUTH_CLIENT_SECRET', 'SENTRY_DSN'}

config = settings.model_dump()

# Mask secrets
for key in SECRETS:
    if key in config:
        config[key] = "***REDACTED***"

print(json.dumps(config, indent=2, default=str))
```

---

## Health Check Endpoints

### Backend Health Check

```bash
# Basic health check
curl http://localhost:8000/api/v1/health

# Expected response
{"status": "healthy", "timestamp": "2024-01-15T10:00:00Z"}
```

### Readiness Check (with dependencies)

```bash
# Check if application is ready to serve traffic
curl http://localhost:8000/api/v1/health/ready

# Response includes dependency status
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "oauth": "configured"
}
```

---

## Validation Automation

### CI/CD Configuration Validation

Add to your CI/CD pipeline:

```yaml
# GitHub Actions example
- name: Validate Configuration
  run: |
    # Check required files exist
    test -f .env.example
    test -f .env.production.example
    test -f .env.staging.example

    # Validate Python settings load
    cd backend
    python -c "from app.core.config import Settings; Settings()"

    # Check for placeholder values
    if grep -E 'CHANGE_ME|TODO|REPLACE' .env.production.example; then
      echo "Placeholder values found in production template"
      exit 1
    fi
```

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Check for secrets in staged files
if git diff --cached --name-only | xargs grep -l -E '(password|secret|key).*=' 2>/dev/null; then
    echo "WARNING: Possible secrets detected in staged files"
    echo "Review and use environment variables instead"
    exit 1
fi
```

---

## Related Documentation

- [Environment Configuration](./environment-configuration.md) - Full variable reference
- [Secrets Management](./secrets-management.md) - Secrets patterns
- [../runbooks/](../runbooks/) - Operational runbooks
- [../DEPLOYMENT.md](../DEPLOYMENT.md) - Deployment procedures

# Keycloak Down Runbook

## Overview

**Alert Name:** KeycloakDown
**Severity:** critical
**Service:** keycloak
**Last Updated:** 

### Description

This alert fires when Keycloak authentication service has been unreachable for 2 minutes. Keycloak is critical for user authentication and authorization.

### Impact

- **New logins blocked**: Users cannot sign in
- **Token refresh may fail**: Existing sessions may expire without renewal
- **JWKS retrieval**: May use cached keys temporarily
- **Signup/registration blocked**: New users cannot create accounts

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/keycloak/keycloak-overview |
| **Logs** | `{container="keycloak"}` |
| **Metrics** | `up{job="keycloak"}` |
| **Escalation** | Infrastructure team |
| **Admin Console** | http://localhost:8080/admin |

---

## Diagnosis Steps

### 1. Check Keycloak Status

```bash
# Check container status
docker compose ps keycloak

# Check health endpoint
curl -s http://localhost:8080/health/ready

# Check if port is responding
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080
```

### 2. Check Keycloak Logs

```bash
# Recent logs
docker compose logs --tail=300 keycloak

# Look for startup errors
docker compose logs keycloak | grep -i "error\|exception\|failed"

# Check for database connection issues
docker compose logs keycloak | grep -i "database\|jdbc\|connection"
```

### 3. Check Container Resources

```bash
# Container stats
docker stats --no-stream keycloak

# Check for OOM
docker inspect keycloak --format='{{.State.OOMKilled}} {{.State.ExitCode}}'

# Check container health
docker inspect keycloak --format='{{.State.Health.Status}}'
```

### 4. Check Database Dependency

```bash
# Keycloak uses PostgreSQL
docker compose ps postgres
docker compose exec postgres pg_isready

# Check Keycloak database
docker compose exec postgres psql -U knowledge_mapper_user -d keycloak -c "\dt"
```

### 5. Check Network

```bash
# Test network between containers
docker compose exec keycloak ping -c 2 postgres

# Check if Keycloak can reach database
docker compose logs keycloak | tail -50 | grep -i "datasource\|connection"
```

---

## Resolution Steps

### Option A: Restart Keycloak

**When to use:** Transient issue, service stuck

```bash
# Restart Keycloak
docker compose restart keycloak

# Wait for startup (Keycloak takes ~30-60 seconds)
sleep 60

# Verify health
curl -s http://localhost:8080/health/ready

# Check logs for successful start
docker compose logs --tail=20 keycloak
```

**Expected outcome:** Health endpoint returns ready status

### Option B: Restart Database First

**When to use:** Database connection errors in logs

```bash
# Restart PostgreSQL
docker compose restart postgres

# Wait for database
sleep 10
docker compose exec postgres pg_isready

# Then restart Keycloak
docker compose restart keycloak

# Wait and verify
sleep 60
curl -s http://localhost:8080/health/ready
```

### Option C: Recreate Keycloak Container

**When to use:** Container state corrupted

```bash
# Stop and remove
docker compose stop keycloak
docker compose rm -f keycloak

# Recreate
docker compose up -d keycloak

# Monitor startup
docker compose logs -f keycloak
```

### Option D: Clear Keycloak Cache

**When to use:** Stale cache causing issues

```bash
# Access Keycloak CLI (if container is running but unhealthy)
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh \
  config credentials --server http://localhost:8080 \
  --realm master --user admin --password admin

# Clear caches via admin API
# This requires admin access
```

Alternatively, restart with cache clear:

```bash
# Stop Keycloak
docker compose stop keycloak

# Start with cache clear (environment variable)
KEYCLOAK_CACHE_TYPE=local docker compose up -d keycloak
```

### Option E: Increase Memory

**When to use:** OOM kills, heap exhaustion

Edit `compose.yml`:

```yaml
keycloak:
  environment:
    - JAVA_OPTS=-Xms512m -Xmx1024m
```

```bash
# Apply new configuration
docker compose up -d keycloak
```

### Option F: Fix Database Connection

**When to use:** Database connectivity issues

```bash
# Check PostgreSQL is accepting connections
docker compose exec postgres psql -U knowledge_mapper_user -c "SELECT 1"

# Check Keycloak database exists
docker compose exec postgres psql -U knowledge_mapper_user -c "\l" | grep keycloak

# Create if missing
docker compose exec postgres psql -U knowledge_mapper_user -c "CREATE DATABASE keycloak;"
```

---

## Verify Recovery

After resolution:

```bash
# Health check
curl -s http://localhost:8080/health/ready | jq .

# Test realm discovery
curl -s http://localhost:8080/realms/knowledge-mapper-dev/.well-known/openid-configuration | jq .issuer

# Test JWKS endpoint (used by backend)
curl -s http://localhost:8080/realms/knowledge-mapper-dev/protocol/openid-connect/certs | jq .

# Test login page loads
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/realms/knowledge-mapper-dev/account"
```

---

## Escalation

### When to Escalate

- [ ] Keycloak not recovering after multiple restart attempts
- [ ] Database corruption suspected
- [ ] Realm or client configuration issues
- [ ] Multiple environments affected
- [ ] Need to restore from backup

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| Infrastructure | [Configure in your org] | Slack #infrastructure |
| Identity Team | [Configure in your org] | Slack #identity |
| On-Call Engineer | [Configure in your org] | PagerDuty |

---

## Common Root Causes

1. **Memory exhaustion** - Java heap too small, OOM killed
2. **Database unavailable** - PostgreSQL down or unreachable
3. **Network issues** - Docker network problems
4. **Disk full** - Cannot write logs or temp files
5. **Long startup time** - Health check timeout too short
6. **Configuration error** - Bad environment variables

---

## Backend Resilience

The backend handles Keycloak unavailability:

```python
# JWKS caching
# - Public keys are cached in memory
# - Token validation continues with cached keys
# - Cache expires after configured TTL

# Token validation
# - Existing valid tokens continue to work
# - Token expiration enforced locally
# - New logins blocked until Keycloak recovers
```

---

## Post-Incident

1. [ ] Document root cause
2. [ ] Review resource limits (memory, CPU)
3. [ ] Check health check configuration
4. [ ] Validate backup/restore procedure
5. [ ] Consider Keycloak clustering for HA

---

## Related Resources

- [Keycloak Administration Guide](../guides/keycloak-admin.md)
- [Authentication Architecture](../architecture/authentication.md)
- [ADR-017: Observability Stack](../adr/017-optional-observability-stack.md)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

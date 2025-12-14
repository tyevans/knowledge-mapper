# Service Down Runbook

## Overview

**Alert Name:** BackendDown / KeycloakDown / ServiceDown
**Severity:** critical
**Service:** backend, keycloak, or any monitored service
**Last Updated:** 

### Description

This alert fires when a critical service becomes unreachable and Prometheus cannot scrape metrics for 1-2 minutes. This is an urgent situation requiring immediate attention.

### Impact

- **Backend down:** All API requests fail, users cannot interact with the application
- **Keycloak down:** New logins blocked, token refresh may fail
- **Generic service down:** Dependent services may cascade to failure

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/infrastructure |
| **Logs** | `{container=~"backend\|keycloak"}` |
| **Metrics** | `up{job="backend"}`, `up{job="keycloak"}` |
| **Escalation** | Immediate - Infrastructure team |

---

## Diagnosis Steps

### 1. Verify Service Status

```bash
# Check all containers
docker compose ps

# Check specific service
docker compose ps backend
docker compose ps keycloak
```

### 2. Check Container Logs

```bash
# Recent logs (look for crash/exit reasons)
docker compose logs --tail=200 backend
docker compose logs --tail=200 keycloak

# Check for OOM or crash
docker inspect backend --format='{{.State.OOMKilled}} {{.State.ExitCode}} {{.State.Error}}'
```

### 3. Check System Resources

```bash
# Host disk space
df -h

# Docker disk usage
docker system df

# Host memory
free -h

# Container resource limits
docker stats --no-stream
```

### 4. Check Network Connectivity

```bash
# Verify Docker network
docker network ls
docker network inspect knowledge-mapper_default

# Test inter-service connectivity
docker compose exec backend ping -c 2 postgres
```

### 5. Check Dependencies

```bash
# Backend depends on: postgres, redis, keycloak
docker compose ps postgres redis keycloak

# Quick health checks
docker compose exec postgres pg_isready
docker compose exec redis redis-cli ping
```

---

## Resolution Steps

### Option A: Restart Service

**When to use:** Transient crash, OOM without config change

```bash
# Restart specific service
docker compose restart backend

# Or restart with fresh container
docker compose up -d --force-recreate backend

# Verify
docker compose ps backend
curl -s http://localhost:8000/health | jq .
```

### Option B: Recreate Container

**When to use:** Container state is corrupted

```bash
# Stop and remove
docker compose stop backend
docker compose rm -f backend

# Recreate
docker compose up -d backend

# Check logs for startup issues
docker compose logs -f backend
```

### Option C: Fix Disk Space

**When to use:** Disk full causing service failures

```bash
# Clean Docker resources
docker system prune -f

# Remove old images
docker image prune -a -f

# Check specific volumes
docker volume ls
docker volume rm $(docker volume ls -q -f dangling=true)
```

### Option D: Fix Memory Issues

**When to use:** OOM kills, memory pressure

```bash
# Check current limits
docker compose config | grep -A5 deploy

# Increase memory limit (edit compose.yml)
# deploy:
#   resources:
#     limits:
#       memory: 1G

# Restart with new limits
docker compose up -d backend
```

### Option E: Rebuild Container

**When to use:** Corrupted image, dependency issues

```bash
# Rebuild from scratch
docker compose build --no-cache backend

# Start fresh
docker compose up -d backend
```

---

## Keycloak-Specific Steps

### Check Keycloak Health

```bash
# Health endpoint
curl -s http://localhost:8080/health/ready

# Check Keycloak database connection
docker compose logs keycloak | grep -i database
```

### Keycloak Recovery

```bash
# Restart Keycloak
docker compose restart keycloak

# If database is the issue
docker compose restart postgres
sleep 10
docker compose restart keycloak
```

---

## Backend-Specific Steps

### Check Backend Health

```bash
# Health endpoint
curl -s http://localhost:8000/health | jq .

# Check readiness
curl -s http://localhost:8000/health/ready | jq .
```

### Backend Recovery

```bash
# Restart backend
docker compose restart backend

# Force recreate if state is corrupted
docker compose up -d --force-recreate backend
```

---

## Escalation

### When to Escalate

- [ ] Service not recovering after restart attempts
- [ ] Underlying infrastructure issue (disk, network, host)
- [ ] Database corruption suspected
- [ ] Multiple services affected simultaneously
- [ ] Issue recurring after resolution

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| On-Call | [Configure in your org] | PagerDuty/Slack |
| Infrastructure | [Configure in your org] | Slack #infrastructure |
| Database Admin | [Configure in your org] | Slack DM |

---

## Common Root Causes

1. **OOM Kill** - Container exceeded memory limit
2. **Disk Full** - No space for logs, temporary files
3. **Dependency Failure** - Database, Redis, Keycloak not available
4. **Network Issues** - Docker network problems, DNS failures
5. **Bad Deployment** - Recent code change causing crash
6. **Resource Limits** - CPU throttling, insufficient resources

---

## Post-Incident

1. [ ] Document root cause (OOM, disk, crash, etc.)
2. [ ] Review resource limits
3. [ ] Consider adding health check improvements
4. [ ] Update monitoring thresholds if needed
5. [ ] Schedule post-incident review for production incidents

---

## Related Resources

- [Docker Compose Reference](../deployment/docker-compose.md)
- [Infrastructure Architecture](../architecture/infrastructure.md)
- [Keycloak Administration](../guides/keycloak-admin.md)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

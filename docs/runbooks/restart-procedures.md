# Restart Procedures Runbook

## Overview

**Purpose:** Standard restart procedures for all services
**Severity:** N/A (Operational)
**Service:** All services
**Last Updated:** 

### Description

This runbook provides safe restart procedures for each service in the stack. Follow these procedures to minimize downtime and avoid data corruption.

---

## Quick Reference

| Service | Restart Command | Downtime | Dependencies |
|---------|-----------------|----------|--------------|
| Backend | `docker compose restart backend` | ~10s | postgres, redis, keycloak |
| Frontend | `docker compose restart frontend` | ~5s | backend |
| PostgreSQL | `docker compose restart postgres` | ~30s | None (others depend on it) |
| Redis | `docker compose restart redis` | ~5s | None (backend depends on it) |
| Keycloak | `docker compose restart keycloak` | ~60s | postgres |
| Prometheus | `docker compose restart prometheus` | ~10s | None |
| Grafana | `docker compose restart grafana` | ~10s | prometheus, loki |
| Loki | `docker compose restart loki` | ~10s | None |
| Tempo | `docker compose restart tempo` | ~10s | None |

---

## Pre-Restart Checklist

Before restarting any service:

- [ ] Notify team in appropriate channel
- [ ] Check current system health
- [ ] Verify backups are recent (for database restarts)
- [ ] Confirm no critical operations in progress
- [ ] Have rollback plan ready

---

## Backend Restart

### Graceful Restart

```bash
# Check current status
docker compose ps backend
curl -s http://localhost:8000/health | jq .

# Graceful restart
docker compose restart backend

# Wait for startup
sleep 10

# Verify health
curl -s http://localhost:8000/health | jq .
docker compose logs --tail=20 backend
```

### Force Restart (If Unresponsive)

```bash
# Stop the container
docker compose stop backend

# Remove container (keeps volumes)
docker compose rm -f backend

# Start fresh
docker compose up -d backend

# Monitor startup
docker compose logs -f backend
```

### Full Rebuild

```bash
# Rebuild image (after code changes)
docker compose build backend

# Recreate container with new image
docker compose up -d --force-recreate backend

# Verify
curl -s http://localhost:8000/health | jq .
```

---

## Frontend Restart

### Standard Restart

```bash
# Check current status
docker compose ps frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173

# Restart
docker compose restart frontend

# Verify
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173
```

### After Build Changes

```bash
# Rebuild frontend
docker compose build frontend

# Restart with new build
docker compose up -d --force-recreate frontend
```

---

## PostgreSQL Restart

### Important Considerations

- PostgreSQL restart affects all dependent services
- Ensure no active transactions before restart
- Backend will automatically reconnect

### Check Before Restart

```bash
# Check active connections
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT count(*) as connections,
       count(*) FILTER (WHERE state = 'active') as active
FROM pg_stat_activity;
"

# Check for active transactions
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT count(*) FROM pg_stat_activity
WHERE state = 'idle in transaction';
"
```

### Graceful Restart

```bash
# Stop accepting new connections
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'knowledge-mapper'
AND pid <> pg_backend_pid();
"

# Restart PostgreSQL
docker compose restart postgres

# Wait for startup
sleep 10

# Verify
docker compose exec postgres pg_isready

# Restart dependent services
docker compose restart backend keycloak
```

### With Checkpoint

```bash
# Force a checkpoint before restart (safer)
docker compose exec postgres psql -U knowledge_mapper_user -c "CHECKPOINT;"

# Restart
docker compose restart postgres

# Verify
docker compose exec postgres pg_isready
```

---

## Redis Restart

### Standard Restart

```bash
# Check current status
docker compose exec redis redis-cli ping

# Check memory/keys
docker compose exec redis redis-cli info memory
docker compose exec redis redis-cli info keyspace

# Restart
docker compose restart redis

# Verify
docker compose exec redis redis-cli ping
```

### With Persistence Check

```bash
# Trigger save before restart
docker compose exec redis redis-cli BGSAVE

# Wait for save to complete
docker compose exec redis redis-cli LASTSAVE

# Restart
docker compose restart redis

# Verify persistence loaded
docker compose exec redis redis-cli info keyspace
```

---

## Keycloak Restart

### Standard Restart

```bash
# Check current status
docker compose ps keycloak
curl -s http://localhost:8080/health/ready

# Restart (takes ~60 seconds)
docker compose restart keycloak

# Wait for startup
sleep 60

# Verify
curl -s http://localhost:8080/health/ready
```

### After Configuration Changes

```bash
# Rebuild with new config
docker compose build keycloak

# Restart
docker compose up -d --force-recreate keycloak

# Monitor startup
docker compose logs -f keycloak
```

---


## Observability Stack Restart

### Prometheus

```bash
# Restart Prometheus
docker compose restart prometheus

# Verify targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets | length'
```

### Grafana

```bash
# Restart Grafana
docker compose restart grafana

# Verify
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health
```

### Loki

```bash
# Restart Loki
docker compose restart loki

# Verify
curl -s http://localhost:3100/ready
```

### Tempo

```bash
# Restart Tempo
docker compose restart tempo

# Verify
curl -s http://localhost:3200/ready
```

### Full Observability Stack

```bash
# Restart all observability services
docker compose restart prometheus grafana loki tempo promtail

# Verify all healthy
docker compose ps | grep -E "prometheus|grafana|loki|tempo|promtail"
```


---

## Full Stack Restart

### Ordered Restart (Recommended)

```bash
# 1. Stop all services
docker compose down

# 2. Start infrastructure first
docker compose up -d postgres redis

# 3. Wait for databases
sleep 10
docker compose exec postgres pg_isready
docker compose exec redis redis-cli ping

# 4. Start authentication
docker compose up -d keycloak
sleep 60
curl -s http://localhost:8080/health/ready

# 5. Start application services
docker compose up -d backend frontend

# 6. Verify
docker compose ps
curl -s http://localhost:8000/health | jq .


# 7. Start observability (if enabled)
docker compose up -d prometheus grafana loki tempo promtail

```

### Quick Full Restart

```bash
# For development/non-production
docker compose restart

# Verify all services
docker compose ps
```

---

## Rolling Restart (Kubernetes)

```bash
# Trigger rolling restart
kubectl rollout restart deployment/backend

# Monitor progress
kubectl rollout status deployment/backend

# Check pods
kubectl get pods -l app=backend -w
```

---

## Rollback Procedures

### Docker Compose Rollback

```bash
# If new version fails, revert to previous
docker compose pull backend:previous-tag

# Or rebuild from previous commit
git checkout HEAD~1 -- backend/
docker compose build backend
docker compose up -d --force-recreate backend
```

### Kubernetes Rollback

```bash
# Check rollout history
kubectl rollout history deployment/backend

# Rollback to previous version
kubectl rollout undo deployment/backend

# Or rollback to specific revision
kubectl rollout undo deployment/backend --to-revision=2
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs --tail=100 <service>

# Check for port conflicts
lsof -i :8000

# Check disk space
df -h

# Check Docker resources
docker system df
```

### Service Starts Then Crashes

```bash
# Check exit code
docker inspect <container> --format='{{.State.ExitCode}}'

# Check OOM
docker inspect <container> --format='{{.State.OOMKilled}}'

# Check resource limits
docker stats --no-stream
```

---

## Post-Restart Verification

After any restart:

- [ ] Service responds to health checks
- [ ] Logs show successful startup
- [ ] Dependent services are connected
- [ ] Monitor for errors in logs
- [ ] Verify key functionality works

---

## Related Resources

- [Service Down Runbook](./service-down.md)
- [Scaling Runbook](./scaling.md)
- [Docker Compose Reference](../deployment/docker-compose.md)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

# High Latency Runbook

## Overview

**Alert Name:** HighLatency
**Severity:** warning
**Service:** backend
**Last Updated:** 

### Description

This alert fires when 95th percentile response time exceeds 2 seconds for 5 consecutive minutes. This indicates degraded performance affecting user experience.

### Impact

- Slow page loads and API responses
- Potential timeout errors on client side
- Poor user experience

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/backend/backend-overview |
| **Logs** | `{container="backend"} \| json \| latency > 2000` |
| **Metrics** | `http_request_duration_seconds_bucket` |
| **Escalation** | Backend team |

---

## Diagnosis Steps

### 1. Check Current Latency Distribution

```bash
# View p50, p90, p95, p99 latencies in Prometheus
# http://localhost:9090/graph?g0.expr=histogram_quantile(0.95,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))
```

### 2. Identify Slow Endpoints

```bash
# Check per-endpoint latency
# Prometheus query: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, path))

# Check logs for slow requests
docker compose logs --tail=500 backend | grep -E "latency.*[0-9]{4,}ms"
```

### 3. Check Database Performance

```bash
# Check slow queries in PostgreSQL
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY duration DESC
LIMIT 5;
"

# Check for locks
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT blocked_locks.pid AS blocked_pid,
       blocking_locks.pid AS blocking_pid,
       blocked_activity.query AS blocked_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
WHERE NOT blocked_locks.granted;
"
```

### 4. Check Resource Utilization

```bash
# Container CPU and memory
docker stats --no-stream

# Check for CPU throttling
docker inspect backend --format='{{.HostConfig.CpuQuota}}'
```

### 5. Check External Dependencies

```bash
# Redis latency
docker compose exec redis redis-cli --latency

# Keycloak response time
time curl -s http://localhost:8080/realms/knowledge-mapper-dev/.well-known/openid-configuration > /dev/null
```

---

## Resolution Steps

### Option A: Scale Horizontally

**When to use:** CPU/memory pressure, high request volume

```bash
# Docker Compose (development)
docker compose up --scale backend=2 -d

# Kubernetes
kubectl scale deployment backend --replicas=3
```

### Option B: Optimize Database Queries

**When to use:** Slow queries identified in logs

```bash
# Enable query logging temporarily
docker compose exec postgres psql -U knowledge_mapper_user -c "
ALTER SYSTEM SET log_min_duration_statement = 500;
SELECT pg_reload_conf();
"

# Check for missing indexes
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename;
"
```

### Option C: Increase Connection Pool

**When to use:** Connection wait times in logs

Update `DATABASE_POOL_SIZE` environment variable:

```bash
# Check current pool settings
docker compose exec backend python -c "from app.core.config import settings; print(settings.DATABASE_POOL_SIZE)"

# Increase pool size (requires restart)
# Edit .env: DATABASE_POOL_SIZE=20
docker compose restart backend
```

### Option D: Redis Cache Optimization

**When to use:** Cache miss rate high, Redis slow

```bash
# Check Redis memory usage
docker compose exec redis redis-cli info memory

# Check cache hit rate
docker compose exec redis redis-cli info stats | grep keyspace
```

---

## Escalation

### When to Escalate

- [ ] Latency not improving within 20 minutes
- [ ] Database queries are the bottleneck but unclear which
- [ ] Infrastructure scaling needed beyond current limits
- [ ] Third-party service causing delays

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| On-Call Engineer | [Configure in your org] | Slack #oncall |
| Backend Team Lead | [Configure in your org] | Slack DM |
| Database Admin | [Configure in your org] | Slack #database |

---

## Common Root Causes

1. **Slow database queries** - Missing indexes, complex joins, table bloat
2. **Connection pool saturation** - Increase pool size or fix connection leaks
3. **CPU throttling** - Increase container CPU limits
4. **Memory pressure** - GC pauses, increase memory limits
5. **External service latency** - Redis, Keycloak, third-party APIs
6. **N+1 query patterns** - Review ORM usage, add eager loading

---

## Post-Incident

1. [ ] Document slow endpoints identified
2. [ ] Create tickets for query optimization
3. [ ] Review index coverage
4. [ ] Consider caching improvements
5. [ ] Update performance baselines

---

## Related Resources

- [Performance Baselines](../performance/baselines.md)
- [Database Optimization Guide](../guides/database-optimization.md)
- [Grafana Backend Dashboard](http://localhost:3000/d/backend)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

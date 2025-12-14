# High Memory Usage Runbook

## Overview

**Alert Name:** HighMemoryUsage
**Severity:** warning
**Service:** Any container
**Last Updated:** 

### Description

This alert fires when a container's memory usage exceeds 80% of its limit for 5 consecutive minutes. At 100%, the container will be OOM (Out of Memory) killed.

### Impact

- Service restart if OOM killed
- Request failures during restart
- Potential data loss if in-flight operations are interrupted
- Cascading failures to dependent services

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/infrastructure |
| **Logs** | `{container="<container_name>"}` |
| **Metrics** | `container_memory_working_set_bytes`, `container_spec_memory_limit_bytes` |
| **Escalation** | Infrastructure team |

---

## Diagnosis Steps

### 1. Identify the Container

```bash
# Check which container is using high memory
docker stats --no-stream

# Or from the alert, note the container name in $labels.name
```

### 2. Check Current Memory Usage

```bash
# Container memory stats
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Detailed memory info
docker inspect backend --format='{{.HostConfig.Memory}}'
```

### 3. Check for OOM Events

```bash
# Check if container was OOM killed
docker inspect backend --format='{{.State.OOMKilled}}'

# Check system logs for OOM events
dmesg | grep -i "oom\|killed"

# Check Docker events
docker events --since 1h --filter type=container --filter event=oom
```

### 4. Analyze Memory Growth

```bash
# Check Prometheus for memory trend
# container_memory_working_set_bytes{name="backend"}

# Check for memory growth pattern
# rate(container_memory_working_set_bytes{name="backend"}[1h])
```

### 5. Check Application Memory

For Python applications:

```bash
# Check for large objects in memory (if debugging available)
docker compose exec backend python -c "
import gc
gc.collect()
print(f'Objects: {len(gc.get_objects())}')
"
```

---

## Resolution Steps

### Option A: Restart Container

**When to use:** Memory leak, need immediate relief

```bash
# Restart the container to free memory
docker compose restart backend

# Monitor memory after restart
docker stats backend

# Verify service is healthy
curl -s http://localhost:8000/health | jq .
```

### Option B: Increase Memory Limits

**When to use:** Container is legitimately under-resourced

Edit `compose.yml`:

```yaml
backend:
  deploy:
    resources:
      limits:
        memory: 2G  # Increase from current value
      reservations:
        memory: 512M
```

```bash
# Apply new limits
docker compose up -d backend

# Verify new limits
docker inspect backend --format='{{.HostConfig.Memory}}'
```

### Option C: Scale Horizontally

**When to use:** High load causing memory pressure

```bash
# Add more replicas to distribute load
docker compose up --scale backend=3 -d

# Kubernetes
kubectl scale deployment backend --replicas=3
```

### Option D: Trigger Garbage Collection

**When to use:** Python application with GC-related memory growth

```bash
# Force garbage collection (if endpoint available)
curl -X POST http://localhost:8000/debug/gc

# Or via container
docker compose exec backend python -c "import gc; gc.collect(); print('GC completed')"
```

### Option E: Reduce Cache Size

**When to use:** In-memory caches consuming too much memory

```bash
# Check Redis memory (if caching is in Redis)
docker compose exec redis redis-cli info memory

# Clear application caches (if applicable)
docker compose exec backend python -c "from app.core.cache import cache; cache.clear()"
```

### Option F: Fix Memory Leak

**When to use:** Memory leak identified in application

1. Enable memory profiling
2. Identify leaking objects
3. Fix code and deploy
4. Monitor after fix

```bash
# Memory profiling with tracemalloc (Python)
docker compose exec backend python -c "
import tracemalloc
tracemalloc.start()
# ... run operations ...
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')[:10]
for stat in top_stats:
    print(stat)
"
```

---

## Kubernetes-Specific Steps

### Check Pod Status

```bash
# Check for OOMKilled status
kubectl get pods -l app=backend -o wide
kubectl describe pod <pod-name> | grep -A5 "Last State"

# Check container restart count
kubectl get pods -l app=backend -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}'
```

### Check Resource Requests

```bash
# Check memory requests vs limits
kubectl get pods -l app=backend -o jsonpath='{.items[*].spec.containers[*].resources}'

# Check node memory availability
kubectl top nodes
kubectl top pods
```

---

## Escalation

### When to Escalate

- [ ] Memory continues to grow after restart
- [ ] Cannot identify source of memory leak
- [ ] Need infrastructure changes (more memory, larger instances)
- [ ] Application fix required

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| Infrastructure | [Configure in your org] | Slack #infrastructure |
| Backend Team Lead | [Configure in your org] | Slack DM |
| On-Call Engineer | [Configure in your org] | PagerDuty |

---

## Common Root Causes

1. **Memory leak** - Objects not being released
2. **Large request payload** - Processing large files/data
3. **Connection pooling** - Too many pooled connections
4. **Caching** - In-memory cache growing unbounded
5. **Under-provisioned** - Limits too low for workload
6. **Traffic spike** - More concurrent requests = more memory

---

## Prevention

### Application Settings

```python
# Limit connection pool sizes
DATABASE_POOL_SIZE = 10
DATABASE_MAX_OVERFLOW = 5

# Limit in-memory cache size
CACHE_MAX_SIZE = 1000
CACHE_TTL_SECONDS = 300

# Limit request body size
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB
```

### Container Configuration

```yaml
# Set memory limits in compose.yml
deploy:
  resources:
    limits:
      memory: 1G
    reservations:
      memory: 256M
```

---

## Post-Incident

1. [ ] Document memory usage patterns
2. [ ] Right-size container limits
3. [ ] Check for memory leaks in code
4. [ ] Review cache configurations
5. [ ] Update monitoring thresholds

---

## Related Resources

- [Scaling Runbook](./scaling.md)
- [Service Down Runbook](./service-down.md)
- [Infrastructure Dashboard](http://localhost:3000/d/infrastructure)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

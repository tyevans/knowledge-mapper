# High CPU Usage Runbook

## Overview

**Alert Name:** HighCPUUsage
**Severity:** warning
**Service:** Any container
**Last Updated:** 

### Description

This alert fires when a container's CPU usage exceeds 80% of its allocated quota for 5 consecutive minutes. This indicates the container may be under-resourced for its workload.

### Impact

- Increased response latency
- Request queueing and timeouts
- Potential cascading failures to dependent services
- Degraded user experience

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/infrastructure |
| **Logs** | `{container="<container_name>"}` |
| **Metrics** | `container_cpu_usage_seconds_total`, `container_spec_cpu_quota` |
| **Escalation** | Infrastructure team |

---

## Diagnosis Steps

### 1. Identify the Container

```bash
# Check which container is using high CPU
docker stats --no-stream

# Or from the alert, note the container name in $labels.name
```

### 2. Check Current CPU Usage

```bash
# Prometheus query for container CPU usage
# rate(container_cpu_usage_seconds_total{name="backend"}[5m])

# Check container stats
docker stats --no-stream backend
```

### 3. Check Container Limits

```bash
# View current limits
docker inspect backend --format='{{.HostConfig.CpuQuota}} {{.HostConfig.CpuPeriod}}'

# Calculate CPU limit: CpuQuota / CpuPeriod = number of CPUs
# E.g., 100000 / 100000 = 1 CPU
```

### 4. Check for Anomalous Activity

```bash
# Check container logs for errors or unusual patterns
docker compose logs --tail=200 backend | grep -i "error\|exception\|timeout"

# Check request rate (if backend)
# Prometheus: rate(http_requests_total{job="backend"}[5m])
```

### 5. Profile the Application

```bash
# For Python applications
docker compose exec backend python -c "import py_spy; print('py-spy available')"

# Sample process (if py-spy is installed)
docker compose exec backend py-spy top --pid 1

# For general profiling, check if profiling endpoint is available
curl -s http://localhost:8000/debug/pprof/ 2>/dev/null || echo "Profiling not available"
```

---

## Resolution Steps

### Option A: Increase CPU Limits

**When to use:** Legitimate workload increase, container is under-resourced

Edit `compose.yml`:

```yaml
backend:
  deploy:
    resources:
      limits:
        cpus: '2.0'  # Increase from current value
      reservations:
        cpus: '0.5'
```

```bash
# Apply new limits
docker compose up -d backend

# Verify new limits
docker inspect backend --format='{{.HostConfig.CpuQuota}}'
```

### Option B: Scale Horizontally

**When to use:** High request volume, can distribute load

```bash
# Docker Compose
docker compose up --scale backend=3 -d

# Kubernetes
kubectl scale deployment backend --replicas=3
```

### Option C: Optimize Application Code

**When to use:** Inefficient code path identified, CPU-intensive operations

1. Profile to identify hot spots
2. Optimize algorithm or caching
3. Move CPU-intensive work to background tasks
4. Implement request throttling

### Option D: Restart Service

**When to use:** CPU spike is transient, potential memory leak causing GC pressure

```bash
# Restart the affected container
docker compose restart backend

# Monitor CPU after restart
docker stats backend
```

### Option E: Reduce Load

**When to use:** Under attack or unexpected traffic spike

```bash
# Enable rate limiting (if not already)
# Check current rate limits
curl -s http://localhost:8000/metrics | grep rate_limit

# Temporarily block problematic clients (if identifiable)
# This depends on your load balancer configuration
```

---

## Kubernetes-Specific Steps

### Check HPA Status

```bash
# Check if HPA is scaling
kubectl get hpa backend-hpa

# Check HPA events
kubectl describe hpa backend-hpa

# Check if pods are pending (resource constraints)
kubectl get pods -l app=backend
kubectl describe pod <pending-pod-name>
```

### Check Node Resources

```bash
# Check node CPU availability
kubectl top nodes

# Check pod CPU usage
kubectl top pods -l app=backend
```

---

## Escalation

### When to Escalate

- [ ] CPU remains high after scaling
- [ ] Cannot identify cause of CPU usage
- [ ] Infrastructure changes needed (more nodes, larger instances)
- [ ] Application optimization requires code changes

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| Infrastructure | [Configure in your org] | Slack #infrastructure |
| Backend Team Lead | [Configure in your org] | Slack DM |
| On-Call Engineer | [Configure in your org] | PagerDuty |

---

## Common Root Causes

1. **Traffic spike** - Legitimate or attack traffic increase
2. **Inefficient code** - Expensive operations, tight loops
3. **Resource exhaustion** - GC thrashing due to memory pressure
4. **Background jobs** - Scheduled tasks consuming CPU
5. **Under-provisioned** - Limits too low for workload
6. **Dependency issues** - Retrying failed requests repeatedly

---

## Post-Incident

1. [ ] Review CPU usage patterns
2. [ ] Right-size container limits based on data
3. [ ] Consider auto-scaling if not already configured
4. [ ] Profile application for optimization opportunities
5. [ ] Update capacity planning

---

## Related Resources

- [Scaling Runbook](./scaling.md)
- [High Latency Runbook](./high-latency.md)
- [Infrastructure Dashboard](http://localhost:3000/d/infrastructure)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

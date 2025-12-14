# High Error Rate Runbook

## Overview

**Alert Name:** HighErrorRate
**Severity:** critical
**Service:** backend
**Last Updated:** 

### Description

This alert fires when HTTP 5xx error rate exceeds 1% of total requests for 5 consecutive minutes. This indicates a systemic issue beyond occasional transient failures.

### Impact

- Users experiencing errors when making API requests
- Potential data inconsistency if write operations fail
- Degraded user experience and trust

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/backend/backend-overview |
| **Logs** | `{container="backend"} \|= "ERROR"` |
| **Metrics** | `http_requests_total{status=~"5.."}` |
| **Escalation** | Backend team lead |

---

## Diagnosis Steps

### 1. Check Current Error Rate

```bash
# View in Prometheus
# http://localhost:9090/graph?g0.expr=sum(rate(http_requests_total{status=~"5.."}[5m]))/sum(rate(http_requests_total[5m]))
```

### 2. Identify Error Patterns

```bash
# Check recent backend errors
docker compose logs --tail=500 backend | grep -i error

# Check for specific HTTP 5xx patterns
docker compose logs --tail=500 backend | grep -E "HTTP/1.1\" 5[0-9]{2}"
```

### 3. Check Service Health

```bash
# Health endpoint
curl -s http://localhost:8000/health | jq .

# Check container status
docker compose ps backend
```

### 4. Check Downstream Dependencies

```bash
# Database connectivity
docker compose exec backend python -c "from app.db.session import engine; print(engine.execute('SELECT 1').scalar())"

# Redis connectivity
docker compose exec redis redis-cli ping

# Keycloak connectivity
curl -s http://localhost:8080/health/ready
```

### 5. Check Resource Usage

```bash
# Container stats
docker stats --no-stream

# Check for OOM kills
docker inspect backend --format='{{.State.OOMKilled}}'
```

---

## Resolution Steps

### Option A: Restart Backend Service

**When to use:** Transient issue, no obvious root cause, service degraded

```bash
# Graceful restart
docker compose restart backend

# Verify recovery
sleep 10 && curl -s http://localhost:8000/health | jq .
```

**Expected outcome:** Error rate should return to normal within 2-3 minutes

### Option B: Scale Backend Replicas (if using Kubernetes)

**When to use:** Load-related errors, resource exhaustion

```bash
# Scale up replicas
kubectl scale deployment backend --replicas=3

# Verify pods are running
kubectl get pods -l app=backend
```

### Option C: Fix Database Connection Issues

**When to use:** Database-related errors in logs

```bash
# Check PostgreSQL connections
docker compose exec postgres psql -U knowledge_mapper_user -c "SELECT count(*) FROM pg_stat_activity;"

# Restart database if needed (caution: brief outage)
docker compose restart postgres

# Wait for backend to reconnect
sleep 30 && curl -s http://localhost:8000/health | jq .
```

### Option D: Rollback Recent Deployment

**When to use:** Errors started after recent deployment

```bash
# Check deployment history (Kubernetes)
kubectl rollout history deployment/backend

# Rollback to previous version
kubectl rollout undo deployment/backend

# Verify rollback
kubectl rollout status deployment/backend
```

---

## Escalation

### When to Escalate

- [ ] Issue not resolved within 15 minutes
- [ ] Error rate continues to increase
- [ ] Root cause is unclear after investigation
- [ ] Data integrity issues suspected
- [ ] Multiple services affected

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| On-Call Engineer | [Configure in your org] | Slack #oncall |
| Backend Team Lead | [Configure in your org] | Slack DM |
| Infrastructure | [Configure in your org] | Slack #infrastructure |

---

## Common Root Causes

1. **Database connection exhaustion** - Check pg_stat_activity
2. **Memory pressure** - Check container memory limits
3. **Dependency service failure** - Check Redis, Keycloak
4. **Bad deployment** - Check recent changes
5. **External service timeout** - Check network/DNS

---

## Post-Incident

After resolving:

1. [ ] Document timeline in incident channel
2. [ ] Identify root cause
3. [ ] Create ticket for permanent fix if needed
4. [ ] Consider alert threshold adjustment
5. [ ] Update this runbook with learnings

---

## Related Resources

- [Backend Architecture](../architecture/backend.md)
- [ADR-017: Observability Stack](../adr/017-optional-observability-stack.md)
- [Grafana Backend Dashboard](http://localhost:3000/d/backend)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

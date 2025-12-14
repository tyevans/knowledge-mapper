# Scaling Runbook

## Overview

**Purpose:** Manual scaling procedures for application services
**Severity:** N/A (Proactive)
**Service:** All services
**Last Updated:** 

### Description

This runbook covers procedures for scaling services horizontally and vertically in response to load or resource constraints.

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/infrastructure |
| **Metrics** | Container CPU, Memory, Request rate |
| **Prerequisites** | Docker Compose or Kubernetes access |

---

## When to Scale

### Indicators for Scaling Up

- [ ] CPU usage consistently above 70%
- [ ] Memory usage consistently above 80%
- [ ] Response latency increasing
- [ ] Error rate increasing due to timeouts
- [ ] Request queue growing

### Indicators for Scaling Down

- [ ] CPU usage consistently below 30%
- [ ] Memory usage consistently below 40%
- [ ] Minimal traffic during off-hours
- [ ] Cost optimization requirements

---

## Docker Compose Scaling

### Scale Backend Horizontally

```bash
# Scale to 3 replicas
docker compose up --scale backend=3 -d

# Verify replicas
docker compose ps | grep backend

# Check load distribution (if using nginx)
docker compose logs nginx | grep -E "upstream|backend"
```

**Note:** Docker Compose scaling requires a load balancer (nginx) to distribute traffic.

### Scale Down

```bash
# Scale back to 1 replica
docker compose up --scale backend=1 -d

# Verify
docker compose ps | grep backend
```

### Vertical Scaling (Docker Compose)

Edit `compose.yml` to adjust resource limits:

```yaml
backend:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        cpus: '0.5'
        memory: 512M
```

```bash
# Apply new limits
docker compose up -d backend
```

---

## Kubernetes Scaling

### Scale Backend Horizontally

```bash
# Scale to 3 replicas
kubectl scale deployment backend --replicas=3

# Verify pods
kubectl get pods -l app=backend

# Watch scaling progress
kubectl rollout status deployment/backend

# Check HPA if configured
kubectl get hpa backend
```

### Configure Horizontal Pod Autoscaler (HPA)

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

```bash
# Apply HPA
kubectl apply -f hpa.yaml

# Monitor HPA
kubectl get hpa backend-hpa -w
```

### Vertical Scaling (Kubernetes)

```bash
# Edit deployment resources
kubectl edit deployment backend

# Or apply updated manifest
kubectl apply -f deployment.yaml

# This triggers a rolling update
kubectl rollout status deployment/backend
```

---

## Database Scaling

### PostgreSQL Read Replicas

For read-heavy workloads, add read replicas:

```yaml
# compose.yml addition
postgres-replica:
  image: postgres:18
  environment:
    POSTGRES_USER: knowledge_mapper_user
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  command: |
    postgres
    -c wal_level=replica
    -c hot_standby=on
  volumes:
    - postgres-replica-data:/var/lib/postgresql/data
```

### PostgreSQL Connection Pool (PgBouncer)

```yaml
# compose.yml addition
pgbouncer:
  image: edoburu/pgbouncer
  environment:
    DATABASE_URL: postgres://knowledge_mapper_user:${POSTGRES_PASSWORD}@postgres:5432/knowledge-mapper
    POOL_MODE: transaction
    MAX_CLIENT_CONN: 1000
    DEFAULT_POOL_SIZE: 20
  ports:
    - "6432:6432"
```

---

## Redis Scaling

### Redis Cluster Mode

For high-availability Redis:

```yaml
# redis-cluster.yml
version: '3.8'
services:
  redis-node-1:
    image: redis:7
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000

  redis-node-2:
    image: redis:7
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000

  redis-node-3:
    image: redis:7
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000
```

### Redis Memory Scaling

```bash
# Increase maxmemory
docker compose exec redis redis-cli CONFIG SET maxmemory 1gb

# Or edit compose.yml
# command: redis-server --maxmemory 1gb --maxmemory-policy allkeys-lru
```

---

## Keycloak Scaling

### Keycloak Cluster Mode

For high-availability Keycloak:

```yaml
# compose.yml
keycloak:
  image: quay.io/keycloak/keycloak:26.4
  environment:
    KC_CACHE: ispn
    KC_CACHE_STACK: kubernetes  # or tcp for Docker
    JAVA_OPTS: -Djgroups.dns.query=keycloak
  deploy:
    replicas: 2
```

**Note:** Keycloak clustering requires shared database and cache coordination.

---

## Scaling Checklist

### Before Scaling Up

- [ ] Check current resource usage (CPU, memory)
- [ ] Verify database can handle more connections
- [ ] Confirm Redis has capacity for more clients
- [ ] Check disk space for logs/data
- [ ] Validate load balancer configuration

### After Scaling Up

- [ ] Verify all replicas are healthy
- [ ] Check load distribution is even
- [ ] Monitor error rates for issues
- [ ] Verify database connection pool is sufficient
- [ ] Check latency has improved

### Before Scaling Down

- [ ] Confirm traffic is reduced
- [ ] Verify remaining capacity is sufficient
- [ ] Schedule during low-traffic period
- [ ] Have rollback plan ready

### After Scaling Down

- [ ] Verify service is still healthy
- [ ] Check latency is acceptable
- [ ] Monitor for capacity issues

---

## Capacity Planning

### Resource Recommendations

| Service | Min CPU | Min Memory | Max CPU | Max Memory |
|---------|---------|------------|---------|------------|
| Backend | 0.5 | 512M | 2.0 | 2G |
| Keycloak | 0.5 | 512M | 2.0 | 1G |
| PostgreSQL | 1.0 | 1G | 4.0 | 4G |
| Redis | 0.25 | 256M | 1.0 | 1G |

### Scaling Triggers

| Metric | Scale Up | Scale Down |
|--------|----------|------------|
| CPU % | > 70% for 5m | < 30% for 15m |
| Memory % | > 80% for 5m | < 40% for 15m |
| Request Rate | > 1000 req/s | < 100 req/s |
| Latency p95 | > 1s for 5m | < 200ms for 15m |

---

## Troubleshooting

### Pods Not Starting

```bash
# Check events
kubectl describe pod <pod-name>

# Check resource quotas
kubectl describe resourcequota

# Check node capacity
kubectl describe nodes | grep -A5 "Allocated resources"
```

### Uneven Load Distribution

```bash
# Check pod distribution
kubectl get pods -o wide

# Check service endpoints
kubectl get endpoints <service-name>

# Verify load balancer config
kubectl describe service <service-name>
```

---

## Related Resources

- [Infrastructure Architecture](../architecture/infrastructure.md)
- [High Latency Runbook](./high-latency.md)
- [Service Down Runbook](./service-down.md)
- [Kubernetes HPA Documentation](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

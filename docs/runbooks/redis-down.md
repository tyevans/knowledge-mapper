# Redis Down Runbook

## Overview

**Alert Name:** RedisConnectionFailure / RedisHighMemory
**Severity:** critical / warning
**Service:** redis
**Last Updated:** 

### Description

- **RedisConnectionFailure**: Redis has been unreachable for 1 minute
- **RedisHighMemory**: Redis memory usage exceeds 80% of maxmemory

### Impact

- **Rate limiting** may fail open (allowing more requests than intended)
- **Token revocation** checks fail (revoked tokens may still work temporarily)
- **Caching** unavailable (performance degradation, increased database load)
- **Session storage** unavailable if using Redis for sessions

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/redis/redis-overview |
| **Logs** | `{container="redis"}` |
| **Metrics** | `redis_up`, `redis_memory_used_bytes` |
| **Escalation** | Infrastructure team |

---

## Diagnosis Steps

### 1. Check Redis Status

```bash
# Check container status
docker compose ps redis

# Test Redis connectivity
docker compose exec redis redis-cli ping

# Check Redis info
docker compose exec redis redis-cli info server
```

### 2. Check Redis Logs

```bash
# Recent logs
docker compose logs --tail=200 redis

# Look for specific errors
docker compose logs redis | grep -i "error\|warning\|oom"
```

### 3. Check Memory Usage

```bash
# Memory stats
docker compose exec redis redis-cli info memory

# Key counts per database
docker compose exec redis redis-cli info keyspace

# Memory by key pattern (use with caution in production)
docker compose exec redis redis-cli --scan --pattern '*' | head -20
```

### 4. Check Client Connections

```bash
# Connected clients
docker compose exec redis redis-cli info clients

# List connected clients
docker compose exec redis redis-cli client list
```

### 5. Check Persistence Status

```bash
# RDB and AOF status
docker compose exec redis redis-cli info persistence

# Last save status
docker compose exec redis redis-cli lastsave
```

---

## Resolution Steps

### Option A: Restart Redis

**When to use:** Transient issue, Redis not responding

```bash
# Restart Redis container
docker compose restart redis

# Verify Redis is up
docker compose exec redis redis-cli ping

# Verify backend can connect
docker compose logs --tail=50 backend | grep -i redis
```

**Expected outcome:** Redis responds to ping, backend reconnects automatically

### Option B: Clear Redis Cache

**When to use:** Memory full, need to free space immediately

```bash
# Clear all keys (CAUTION: loses all cached data)
docker compose exec redis redis-cli FLUSHALL

# Or clear only specific database
docker compose exec redis redis-cli FLUSHDB
```

**Expected outcome:** Memory usage drops, application refills cache as needed

### Option C: Remove Specific Keys

**When to use:** Specific key patterns consuming too much memory

```bash
# Find large keys
docker compose exec redis redis-cli --bigkeys

# Delete specific key pattern (one by one)
docker compose exec redis redis-cli KEYS "cache:heavy:*" | xargs -I {} docker compose exec redis redis-cli DEL {}

# Or use SCAN for production (non-blocking)
docker compose exec redis redis-cli --scan --pattern "cache:heavy:*" | xargs -I {} docker compose exec redis redis-cli DEL {}
```

### Option D: Increase Memory Limit

**When to use:** Legitimate need for more cache memory

Edit `compose.yml` or Redis configuration:

```yaml
# In compose.yml
redis:
  command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
```

```bash
# Or at runtime (temporary)
docker compose exec redis redis-cli CONFIG SET maxmemory 512mb
docker compose exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### Option E: Recreate Redis Container

**When to use:** Container state corrupted, persistent issues

```bash
# Stop and remove container (keeps volume data)
docker compose stop redis
docker compose rm -f redis

# Recreate
docker compose up -d redis

# Verify
docker compose exec redis redis-cli ping
```

### Option F: Fix Persistence Issues

**When to use:** RDB/AOF save failures

```bash
# Check disk space
df -h

# Clean up if needed
docker system prune -f

# Trigger manual save
docker compose exec redis redis-cli BGSAVE

# Check save status
docker compose exec redis redis-cli LASTSAVE
```

---

## High Memory Alert Resolution

### Identify Memory Usage

```bash
# Memory breakdown
docker compose exec redis redis-cli INFO memory

# Sample output interpretation:
# used_memory: actual memory used
# used_memory_peak: highest memory used
# maxmemory: configured limit
# maxmemory_policy: eviction policy
```

### Configure Eviction Policy

```bash
# Set eviction policy (if not already set)
docker compose exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Options:
# - noeviction: return errors when memory limit reached
# - allkeys-lru: evict least recently used keys
# - volatile-lru: evict LRU keys with expire set
# - allkeys-random: evict random keys
# - volatile-random: evict random keys with expire set
# - volatile-ttl: evict keys with shortest TTL
```

### Review Key Expiration

```bash
# Check keys without TTL
docker compose exec redis redis-cli SCAN 0 COUNT 100 | xargs -I {} docker compose exec redis redis-cli TTL {}

# Set TTL on keys that should expire
docker compose exec redis redis-cli EXPIRE key_name 3600
```

---

## Escalation

### When to Escalate

- [ ] Redis not recovering after restart
- [ ] Persistent data corruption suspected
- [ ] Memory growth despite eviction policy
- [ ] Cluster issues (if using Redis Cluster)
- [ ] Impact on critical authentication flows

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| Infrastructure | [Configure in your org] | Slack #infrastructure |
| On-Call Engineer | [Configure in your org] | PagerDuty |
| Backend Team Lead | [Configure in your org] | Slack DM |

---

## Common Root Causes

1. **Memory leak** - Keys without TTL accumulating
2. **Sudden traffic spike** - Cache size exceeding limits
3. **Network issues** - Docker network problems
4. **Disk full** - Cannot persist RDB/AOF
5. **Client connection exhaustion** - Too many client connections
6. **Slow commands** - Large operations blocking Redis

---

## Application Resilience

The backend should handle Redis unavailability gracefully:

```python
# Rate limiting fails open
# - Requests are allowed when Redis is down
# - Log warning for monitoring

# Token revocation check fails open
# - Tokens are assumed valid when Redis is down
# - Relies on token expiration for security

# Cache misses go to database
# - Application continues with degraded performance
# - Database load increases
```

---

## Post-Incident

1. [ ] Review memory usage patterns
2. [ ] Check for keys without TTL
3. [ ] Validate eviction policy is appropriate
4. [ ] Consider Redis Cluster if scaling needed
5. [ ] Update monitoring thresholds

---

## Related Resources

- [Redis Configuration Guide](../guides/redis-config.md)
- [Caching Strategy](../architecture/caching.md)
- [Grafana Redis Dashboard](http://localhost:3000/d/redis)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

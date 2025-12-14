# Database Connections Runbook

## Overview

**Alert Name:** DatabaseConnectionPoolExhausted / SQLAlchemyPoolExhausted
**Severity:** critical / warning
**Service:** postgres / backend
**Last Updated:** 

### Description

This alert fires when database connections approach the maximum limit:
- **DatabaseConnectionPoolExhausted**: PostgreSQL connections at 90% of max_connections
- **SQLAlchemyPoolExhausted**: Application connection pool at 90% utilization

### Impact

- New database connections may be rejected
- API requests waiting for connections may timeout
- Application becomes unresponsive or errors increase
- Cascading failures across all services needing database access

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/postgres/postgres-overview |
| **Logs** | `{container="backend"} \|= "connection"` |
| **Metrics** | `pg_stat_activity_count`, `sqlalchemy_pool_checked_out` |
| **Escalation** | Database admin / Backend team |

---

## Diagnosis Steps

### 1. Check Current Connection Count

```bash
# PostgreSQL active connections
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT count(*) as total,
       count(*) FILTER (WHERE state = 'active') as active,
       count(*) FILTER (WHERE state = 'idle') as idle,
       count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
FROM pg_stat_activity;
"

# Check max_connections setting
docker compose exec postgres psql -U knowledge_mapper_user -c "SHOW max_connections;"
```

### 2. Identify Connection Sources

```bash
# Connections by client/application
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT client_addr, application_name, state, count(*)
FROM pg_stat_activity
GROUP BY client_addr, application_name, state
ORDER BY count(*) DESC;
"

# Long-running connections
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT pid, usename, application_name, state,
       now() - backend_start as connection_age,
       now() - query_start as query_age,
       query
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY connection_age DESC
LIMIT 10;
"
```

### 3. Check for Idle in Transaction

```bash
# Find long idle-in-transaction connections
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT pid, usename, state, now() - state_change as idle_time, query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
AND now() - state_change > interval '5 minutes'
ORDER BY idle_time DESC;
"
```

### 4. Check Application Pool Status

```bash
# If using application metrics endpoint
curl -s http://localhost:8000/metrics | grep sqlalchemy_pool

# Check backend logs for connection issues
docker compose logs --tail=200 backend | grep -i "connection\|pool"
```

### 5. Check for Blocking Queries

```bash
# Find blocked and blocking queries
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT blocked_locks.pid AS blocked_pid,
       blocked_activity.usename AS blocked_user,
       blocking_locks.pid AS blocking_pid,
       blocking_activity.usename AS blocking_user,
       blocked_activity.query AS blocked_statement,
       blocking_activity.query AS blocking_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database = blocked_locks.database
    AND blocking_locks.relation = blocked_locks.relation
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
"
```

---

## Resolution Steps

### Option A: Terminate Idle Connections

**When to use:** Many idle or idle-in-transaction connections

```bash
# Terminate idle-in-transaction connections older than 10 minutes
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
AND now() - state_change > interval '10 minutes';
"

# Terminate all idle connections from specific application
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
AND application_name = 'backend'
AND now() - state_change > interval '30 minutes';
"
```

### Option B: Increase max_connections

**When to use:** Legitimate high connection demand

```bash
# Check current setting
docker compose exec postgres psql -U knowledge_mapper_user -c "SHOW max_connections;"

# Edit postgresql.conf or use ALTER SYSTEM
docker compose exec postgres psql -U knowledge_mapper_user -c "
ALTER SYSTEM SET max_connections = 200;
"

# Restart PostgreSQL (will disconnect all clients)
docker compose restart postgres

# Verify new setting
docker compose exec postgres psql -U knowledge_mapper_user -c "SHOW max_connections;"
```

### Option C: Restart Backend Services

**When to use:** Connection leak in application, stale pool

```bash
# Restart backend to reset connection pool
docker compose restart backend

# Verify connections dropped
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT count(*) FROM pg_stat_activity WHERE application_name = 'backend';
"
```

### Option D: Kill Blocking Queries

**When to use:** Long-running queries blocking others

```bash
# Cancel query (graceful)
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT pg_cancel_backend(PID);
"

# Terminate connection (force)
docker compose exec postgres psql -U knowledge_mapper_user -c "
SELECT pg_terminate_backend(PID);
"
```

### Option E: Configure Application Pool

**When to use:** Application pool too large or small

Edit `.env` or environment variables:

```bash
# Reduce pool size if too many connections
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=5

# Or increase if legitimate need
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Restart to apply
docker compose restart backend
```

---

## Escalation

### When to Escalate

- [ ] Cannot identify source of connection leak
- [ ] Issue persists after remediation steps
- [ ] Database needs configuration changes in production
- [ ] Data integrity concerns from terminated queries
- [ ] Multiple applications affected

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| Database Admin | [Configure in your org] | Slack #database |
| Backend Team Lead | [Configure in your org] | Slack DM |
| On-Call Engineer | [Configure in your org] | PagerDuty |

---

## Common Root Causes

1. **Connection leak** - Code not closing connections properly
2. **Slow queries** - Connections held waiting for results
3. **Transaction not committed** - Idle-in-transaction connections
4. **Application scaling** - Too many replicas with large pools
5. **Pool misconfiguration** - Pool size too large or too small
6. **Deadlocks** - Queries blocking each other

---

## Prevention

### Application Configuration

```python
# Recommended SQLAlchemy settings
DATABASE_POOL_SIZE = 5           # Base pool size
DATABASE_MAX_OVERFLOW = 10       # Additional connections allowed
DATABASE_POOL_TIMEOUT = 30       # Wait time for connection
DATABASE_POOL_RECYCLE = 1800     # Recycle connections every 30 min
DATABASE_POOL_PRE_PING = True    # Check connection health
```

### PostgreSQL Configuration

```sql
-- Kill idle connections automatically
ALTER SYSTEM SET idle_in_transaction_session_timeout = '10min';
ALTER SYSTEM SET idle_session_timeout = '30min';
SELECT pg_reload_conf();
```

---

## Post-Incident

1. [ ] Review connection patterns in logs
2. [ ] Check for connection leaks in code
3. [ ] Validate pool size settings
4. [ ] Consider connection pooler (PgBouncer) if needed
5. [ ] Update monitoring thresholds

---

## Related Resources

- [PostgreSQL Connection Management](../guides/postgres-connections.md)
- [SQLAlchemy Pool Configuration](../guides/sqlalchemy-config.md)
- [Grafana PostgreSQL Dashboard](http://localhost:3000/d/postgres)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

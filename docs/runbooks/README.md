# Operational Runbooks

This directory contains operational runbooks for incident response and routine operations.

## Alert-to-Runbook Mapping

| Alert Name | Runbook | Severity | Service |
|------------|---------|----------|---------|
| HighErrorRate | [high-error-rate.md](./high-error-rate.md) | critical | backend |
| HighLatency | [high-latency.md](./high-latency.md) | warning | backend |
| BackendDown | [service-down.md](./service-down.md) | critical | backend |
| KeycloakDown | [keycloak-down.md](./keycloak-down.md) | critical | keycloak |
| DatabaseConnectionPoolExhausted | [db-connections.md](./db-connections.md) | critical | postgres |
| SQLAlchemyPoolExhausted | [db-connections.md](./db-connections.md) | warning | backend |
| RedisConnectionFailure | [redis-down.md](./redis-down.md) | critical | redis |
| RedisHighMemory | [redis-down.md](./redis-down.md) | warning | redis |
| HighCPUUsage | [high-cpu.md](./high-cpu.md) | warning | any |
| HighMemoryUsage | [high-memory.md](./high-memory.md) | warning | any |
| PrometheusAlertingFailure | [prometheus-alerting.md](./prometheus-alerting.md) | critical | prometheus |
| ServiceDown | [service-down.md](./service-down.md) | critical | any |

## Runbook Index

### Incident Response Runbooks

| Runbook | Purpose |
|---------|---------|
| [high-error-rate.md](./high-error-rate.md) | Diagnose and resolve high HTTP 5xx error rates |
| [high-latency.md](./high-latency.md) | Diagnose and resolve high response latency |
| [service-down.md](./service-down.md) | Recover from complete service outages |
| [db-connections.md](./db-connections.md) | Resolve database connection pool exhaustion |
| [redis-down.md](./redis-down.md) | Recover from Redis failures and memory issues |
| [keycloak-down.md](./keycloak-down.md) | Recover from Keycloak authentication outages |
| [high-cpu.md](./high-cpu.md) | Diagnose and resolve high container CPU usage |
| [high-memory.md](./high-memory.md) | Diagnose and resolve high container memory usage |
| [prometheus-alerting.md](./prometheus-alerting.md) | Recover from Prometheus alerting failures |

### Operational Runbooks

| Runbook | Purpose |
|---------|---------|
| [scaling.md](./scaling.md) | Manual scaling procedures for all services |
| [restart-procedures.md](./restart-procedures.md) | Safe restart procedures for all services |

### Post-Incident

| Template | Purpose |
|----------|---------|
| [post-incident-review.md](./post-incident-review.md) | Template for conducting post-incident reviews |

### Creating New Runbooks

Use [_template.md](./_template.md) as a starting point for new runbooks. All runbooks should include:

1. **Overview** - Alert name, severity, service, description, impact
2. **Quick Reference** - Dashboard links, log queries, metrics, escalation
3. **Diagnosis Steps** - Numbered investigation steps
4. **Resolution Steps** - Options (A, B, C) for different root causes
5. **Escalation** - When and who to escalate to
6. **Post-Incident** - Checklist after resolution

## Runbook Design Principles

1. **Actionable** - Every runbook should lead to resolution
2. **Copy-Paste Ready** - Commands should work without modification
3. **Tiered Response** - Start with simple fixes, escalate if needed
4. **Time-Aware** - Include expected timeframes for steps
5. **Living Documents** - Update after each incident where the runbook was used

## Dashboard Links


| Dashboard | URL |
|-----------|-----|
| Infrastructure | http://localhost:3000/d/infrastructure |
| Backend | http://localhost:3000/d/backend |
| PostgreSQL | http://localhost:3000/d/postgres |
| Redis | http://localhost:3000/d/redis |
| Keycloak | http://localhost:3000/d/keycloak |


## Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| On-Call Engineer | [Configure in your org] | PagerDuty / Slack #oncall |
| Backend Team Lead | [Configure in your org] | Slack DM |
| Infrastructure | [Configure in your org] | Slack #infrastructure |
| Database Admin | [Configure in your org] | Slack #database |

**Note:** Update these contacts with your organization's specific information.

## Review Schedule

Runbooks should be reviewed:

- **After each incident** where the runbook was used
- **Quarterly** for accuracy and completeness
- **When related systems change** (architecture, configuration, dependencies)

## Related Documentation

- [Prometheus Alerts](../../observability/prometheus/alerts.yml) - Alert definitions
- [Architecture Overview](../architecture/) - System architecture
- [ADR-017: Observability Stack](../adr/017-optional-observability-stack.md) - Observability decisions

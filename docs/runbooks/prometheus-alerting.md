# Prometheus Alerting Failure Runbook

## Overview

**Alert Name:** PrometheusAlertingFailure
**Severity:** critical
**Service:** prometheus
**Last Updated:** 

### Description

This meta-alert fires when Prometheus fails to send alert notifications. This is critical because it means other alerts may be silently failing.

### Impact

- Alert notifications not being sent
- On-call may not be notified of incidents
- Silent failures - the worst kind
- Other critical alerts going undetected

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | http://localhost:3000/d/prometheus |
| **Logs** | `{container="prometheus"}` |
| **Metrics** | `prometheus_notifications_dropped_total`, `prometheus_notifications_queue_length` |
| **Escalation** | Infrastructure team immediately |

---

## Diagnosis Steps

### 1. Check Prometheus Status

```bash
# Check Prometheus container
docker compose ps prometheus

# Check Prometheus health
curl -s http://localhost:9090/-/healthy

# Check Prometheus ready status
curl -s http://localhost:9090/-/ready
```

### 2. Check Alert Manager Status

```bash
# Check Alertmanager container (if deployed)
docker compose ps alertmanager

# Check Alertmanager health
curl -s http://localhost:9093/-/healthy

# Check Alertmanager ready status
curl -s http://localhost:9093/-/ready
```

### 3. Check Notification Queue

```bash
# Query notification queue length
curl -s "http://localhost:9090/api/v1/query?query=prometheus_notifications_queue_length" | jq .

# Query dropped notifications
curl -s "http://localhost:9090/api/v1/query?query=prometheus_notifications_dropped_total" | jq .
```

### 4. Check Prometheus Logs

```bash
# Recent Prometheus logs
docker compose logs --tail=200 prometheus | grep -i "alert\|error\|fail"

# Check for Alertmanager connection issues
docker compose logs prometheus | grep -i "alertmanager\|notification"
```

### 5. Check Network Connectivity

```bash
# Test connectivity from Prometheus to Alertmanager
docker compose exec prometheus wget -q -O- http://alertmanager:9093/-/healthy

# Check DNS resolution
docker compose exec prometheus nslookup alertmanager
```

---

## Resolution Steps

### Option A: Restart Alertmanager

**When to use:** Alertmanager is unhealthy or unresponsive

```bash
# Restart Alertmanager
docker compose restart alertmanager

# Wait for startup
sleep 10

# Verify health
curl -s http://localhost:9093/-/healthy
```

### Option B: Restart Prometheus

**When to use:** Prometheus notification queue is stuck

```bash
# Restart Prometheus
docker compose restart prometheus

# Wait for startup
sleep 15

# Verify health
curl -s http://localhost:9090/-/ready

# Check notifications are flowing
curl -s "http://localhost:9090/api/v1/query?query=prometheus_notifications_dropped_total" | jq .
```

### Option C: Fix Alertmanager Configuration

**When to use:** Configuration error in Alertmanager

```bash
# Check Alertmanager config
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml

# Validate configuration syntax
docker compose exec alertmanager amtool config show

# If config is invalid, fix and restart
docker compose restart alertmanager
```

### Option D: Fix Prometheus Alerting Configuration

**When to use:** Prometheus cannot reach Alertmanager

Check `prometheus.yml`:

```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093  # Ensure this is correct
```

```bash
# Reload Prometheus configuration
curl -X POST http://localhost:9090/-/reload

# Or restart
docker compose restart prometheus
```

### Option E: Check Network Issues

**When to use:** Network connectivity problems

```bash
# Check Docker network
docker network ls
docker network inspect knowledge-mapper_default

# Ensure both containers are on same network
docker inspect prometheus --format='{{.NetworkSettings.Networks}}'
docker inspect alertmanager --format='{{.NetworkSettings.Networks}}'
```

### Option F: Clear Notification Queue

**When to use:** Queue is backed up with old notifications

```bash
# Restart Prometheus to clear queue
docker compose restart prometheus

# Monitor queue length after restart
watch 'curl -s "http://localhost:9090/api/v1/query?query=prometheus_notifications_queue_length" | jq .data.result[].value[1]'
```

---

## Verify Alerting is Working

### Send Test Alert

```bash
# Trigger a test alert via Alertmanager API
curl -X POST -H "Content-Type: application/json" \
  -d '[{"labels":{"alertname":"TestAlert","severity":"info"},"annotations":{"summary":"Test alert to verify alerting pipeline"}}]' \
  http://localhost:9093/api/v1/alerts

# Check alert is received
curl -s http://localhost:9093/api/v1/alerts | jq .
```

### Check Alert Status in Prometheus

```bash
# List active alerts
curl -s http://localhost:9090/api/v1/alerts | jq .

# List firing alerts
curl -s "http://localhost:9090/api/v1/query?query=ALERTS{alertstate=\"firing\"}" | jq .
```

---

## Escalation

### When to Escalate

- [ ] Alertmanager cannot be recovered
- [ ] Network issues beyond container scope
- [ ] Configuration issues require infrastructure changes
- [ ] External notification channels (Slack, PagerDuty) not working

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| Infrastructure | [Configure in your org] | Direct message (since alerting is down) |
| On-Call Engineer | [Configure in your org] | Phone call directly |
| Platform Team | [Configure in your org] | Direct message |

**IMPORTANT:** Since alerting is broken, use direct communication methods (phone, direct message) rather than relying on automated notifications.

---

## Common Root Causes

1. **Alertmanager down** - Container crashed or OOM
2. **Network issues** - DNS or connectivity problems
3. **Configuration error** - Invalid YAML or wrong endpoints
4. **Resource exhaustion** - Disk full, memory pressure
5. **Queue overflow** - Too many alerts overwhelming system
6. **External service failure** - Slack, PagerDuty, email service down

---

## Temporary Workarounds

While fixing the alerting pipeline:

### Manual Alert Checking

```bash
# Create a script to check alerts manually
cat > /tmp/check-alerts.sh << 'EOF'
#!/bin/bash
alerts=$(curl -s http://localhost:9090/api/v1/alerts | jq -r '.data.alerts[] | select(.state == "firing") | .labels.alertname')
if [ -n "$alerts" ]; then
  echo "FIRING ALERTS:"
  echo "$alerts"
fi
EOF
chmod +x /tmp/check-alerts.sh

# Run periodically
watch -n 60 /tmp/check-alerts.sh
```

### Direct Notification

```bash
# If alerts are firing, manually notify team
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Manual Alert: Prometheus alerting is down, checking alerts manually"}' \
  YOUR_SLACK_WEBHOOK_URL
```

---

## Post-Incident

1. [ ] Verify all alert channels are working
2. [ ] Send test alerts through entire pipeline
3. [ ] Review dropped notification count
4. [ ] Check for any missed alerts during outage
5. [ ] Update alerting redundancy if needed

---

## Related Resources

- [Prometheus Configuration](../../observability/prometheus/prometheus.yml)
- [Alertmanager Configuration](../../observability/alertmanager/alertmanager.yml)
- [Alert Rules](../../observability/prometheus/alerts.yml)
- [Grafana Dashboard](http://localhost:3000/d/prometheus)

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial creation |

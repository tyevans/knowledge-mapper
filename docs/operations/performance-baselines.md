# Performance Baselines

This document defines performance expectations and baseline measurements for Knowledge Mapper.

## Overview

Performance baselines establish expected behavior under normal conditions. They enable:

- **Regression Detection**: Identify when changes degrade performance
- **Capacity Planning**: Understand system limits and scaling needs
- **SLA Definition**: Set realistic performance targets
- **Incident Response**: Know what "normal" looks like for faster diagnosis

## Table of Contents

- [Key Performance Indicators](#key-performance-indicators-kpis)
- [Endpoint-Specific Baselines](#endpoint-specific-baselines)
- [Baseline Measurement Methodology](#baseline-measurement-methodology)
- [Establishing Your Baselines](#establishing-your-baselines)
- [Performance Regression Detection](#performance-regression-detection)
- [Capacity Planning](#capacity-planning)
- [Alerting Thresholds](#alerting-thresholds)
- [Baseline History](#baseline-history)
- [Related Documentation](#related-documentation)

---

## Key Performance Indicators (KPIs)

### Response Time Metrics

| Metric | Target | Warning | Critical | Description |
|--------|--------|---------|----------|-------------|
| **P50 Latency** | < 100ms | < 150ms | < 200ms | Median response time (50th percentile) |
| **P95 Latency** | < 300ms | < 400ms | < 500ms | 95th percentile response time |
| **P99 Latency** | < 500ms | < 750ms | < 1000ms | 99th percentile response time |
| **Max Latency** | < 2000ms | < 3000ms | < 5000ms | Maximum observed response time |

**Why percentiles matter:**
- P50 represents typical user experience
- P95 captures most user experiences including slower ones
- P99 identifies outliers and potential issues
- Averages can hide problems (a few slow requests don't affect average much)

### Throughput Metrics

| Metric | Target | Warning | Critical | Description |
|--------|--------|---------|----------|-------------|
| **Requests/Second** | > 100 | > 75 | > 50 | Sustained request rate per backend instance |
| **Peak RPS** | > 500 | > 300 | > 200 | Maximum burst capacity |
| **Concurrent Users** | > 100 | > 75 | > 50 | Simultaneous active sessions |

### Reliability Metrics

| Metric | Target | Warning | Critical | Description |
|--------|--------|---------|----------|-------------|
| **Error Rate** | < 0.1% | < 0.5% | < 1% | Percentage of failed requests (4xx/5xx) |
| **Availability** | > 99.9% | > 99.5% | > 99% | Uptime percentage |
| **Success Rate** | > 99.9% | > 99.5% | > 99% | Successful transaction rate |
| **Check Pass Rate** | > 99% | > 97% | > 95% | k6 check assertions passing |

### Resource Utilization

| Resource | Normal | Warning | Critical | Description |
|----------|--------|---------|----------|-------------|
| **CPU** | < 50% | < 70% | < 85% | Per-container CPU usage |
| **Memory** | < 60% | < 75% | < 90% | Per-container memory usage |
| **DB Connections** | < 50% | < 70% | < 85% | Percentage of connection pool used |
| **Redis Connections** | < 50% | < 70% | < 85% | Redis client connections |
| **Disk I/O** | < 60% | < 75% | < 90% | Database disk utilization |

---

## Endpoint-Specific Baselines

### Health Endpoints (Low Latency Required)

| Endpoint | P50 | P95 | P99 | Target RPS | Notes |
|----------|-----|-----|-----|------------|-------|
| `GET /api/v1/health` | < 10ms | < 25ms | < 50ms | 1000+ | Simple health check |
| `GET /api/v1/health/ready` | < 20ms | < 50ms | < 100ms | 500+ | Includes DB/Redis check |
| `GET /api/v1/health/live` | < 5ms | < 15ms | < 30ms | 1000+ | Minimal liveness probe |

### Authentication Endpoints

| Endpoint | P50 | P95 | P99 | Target RPS | Notes |
|----------|-----|-----|-----|------------|-------|
| `POST /api/v1/auth/token` | < 100ms | < 200ms | < 400ms | 50+ | Token exchange (Keycloak round-trip) |
| `POST /api/v1/auth/refresh` | < 50ms | < 100ms | < 200ms | 100+ | Token refresh |
| `GET /api/v1/auth/me` | < 30ms | < 75ms | < 150ms | 200+ | JWT validation only |
| `POST /api/v1/auth/logout` | < 50ms | < 100ms | < 200ms | 100+ | Token revocation |

### API Endpoints (CRUD Operations)

| Endpoint | P50 | P95 | P99 | Target RPS | Notes |
|----------|-----|-----|-----|------------|-------|
| `GET /api/v1/todos` | < 50ms | < 100ms | < 200ms | 200+ | List with pagination |
| `POST /api/v1/todos` | < 75ms | < 150ms | < 300ms | 100+ | Create operation |
| `GET /api/v1/todos/{id}` | < 30ms | < 75ms | < 150ms | 300+ | Single item fetch |
| `PUT /api/v1/todos/{id}` | < 75ms | < 150ms | < 300ms | 100+ | Update operation |
| `DELETE /api/v1/todos/{id}` | < 50ms | < 100ms | < 200ms | 150+ | Delete operation |

### Baseline Assumptions

These baselines assume:

- **Environment**: Staging or production-equivalent
- **Database Size**: < 100,000 records per tenant
- **Network Latency**: < 10ms between services
- **Container Resources**: 2 CPU cores, 2GB RAM per backend instance
- **Concurrent Load**: 50 virtual users

---

## Baseline Measurement Methodology

### Test Environment Requirements

Performance baselines must be measured in a consistent, isolated environment:

```yaml
Environment Configuration:
  type: Staging (production-equivalent)
  isolation: Dedicated resources, no shared load

Database:
  type: PostgreSQL 15+
  resources: Dedicated instance (not shared)
  data: Representative dataset loaded

Redis:
  type: Redis 7+
  resources: Dedicated instance

Backend Container:
  cpu: 2 cores
  memory: 2GB RAM
  replicas: 1 (for baseline measurement)

Network:
  latency: < 10ms to database
  bandwidth: Adequate for test load

External Services:
  keycloak: Running and responsive
  status: All services healthy
```

### Pre-Test Checklist

Before running baseline tests:

- [ ] Environment is isolated (no other traffic)
- [ ] All services are healthy (`/health/ready` returns 200)
- [ ] Database has been warmed up (connection pool established)
- [ ] Redis connection pool is established
- [ ] No pending migrations or background jobs
- [ ] Monitoring is active to capture metrics
- [ ] Previous test results are archived

### Test Scenarios for Baselines

Run these scenarios in order:

#### 1. Smoke Test (Validation)

```bash
./scripts/load-test.sh smoke
```

**Purpose**: Verify system is functional before longer tests
**Duration**: ~1 minute
**Pass criteria**: 100% success rate, no errors

#### 2. Baseline Load Test (Primary)

```bash
./scripts/load-test.sh load --vus 50 --duration 10m
```

**Purpose**: Establish baseline metrics under normal load
**Duration**: 10 minutes
**Key metrics**: P50, P95, P99 latency, throughput, error rate

#### 3. Stress Test (Limits)

```bash
./scripts/load-test.sh stress
```

**Purpose**: Find system breaking points
**Duration**: ~25 minutes (ramping)
**Key metrics**: Max sustainable RPS, breaking point VU count

#### 4. Soak Test (Stability)

```bash
./scripts/load-test.sh soak --duration 30m
```

**Purpose**: Detect memory leaks and long-term issues
**Duration**: 30+ minutes
**Key metrics**: Memory growth, latency stability over time

---

## Establishing Your Baselines

### Step 1: Initial Measurement

Deploy to a consistent environment and run initial tests:

```bash
# Ensure clean state
./scripts/docker-dev.sh reset
./scripts/docker-dev.sh up

# Wait for services to be ready
sleep 30

# Run baseline test
./scripts/load-test.sh load --vus 50 --duration 10m \
    --output results/baseline-$(date +%Y%m%d)-run1.json
```

### Step 2: Multiple Runs for Accuracy

Run the baseline test at least 3 times to account for variance:

```bash
for i in 1 2 3; do
    echo "=== Run $i of 3 ==="
    ./scripts/load-test.sh load --vus 50 --duration 10m \
        --output results/baseline-run-$i.json

    # Cool down between runs
    echo "Cooling down for 60 seconds..."
    sleep 60
done
```

### Step 3: Calculate Thresholds

From multiple runs, calculate thresholds using this methodology:

```
Target Calculation:
  P95 Target = average(run1_p95, run2_p95, run3_p95)
  Round up to nearest 10ms or 50ms

Warning Calculation:
  P95 Warning = Target * 1.3  (30% above target)

Critical Calculation:
  P99 Critical = max(run1_p99, run2_p99, run3_p99) * 1.2  (20% buffer)
  Round up to nearest 50ms or 100ms
```

**Example calculation:**

```
Run 1: P95=145ms, P99=285ms
Run 2: P95=152ms, P99=312ms
Run 3: P95=148ms, P99=298ms

P95 Target = avg(145, 152, 148) = 148ms -> Round to 150ms
P95 Warning = 150 * 1.3 = 195ms -> Round to 200ms
P99 Critical = max(285, 312, 298) * 1.2 = 374ms -> Round to 400ms
```

### Step 4: Record Baseline Results

Create a baseline record in JSON format:

```json
{
    "baseline_id": "2024-01-15-001",
    "test_date": "2024-01-15T10:30:00Z",
    "environment": "staging",
    "git_commit": "abc123def456",
    "git_branch": "main",
    "scenario": "load",
    "configuration": {
        "vus": 50,
        "duration": "10m",
        "backend_replicas": 1,
        "backend_cpu": "2000m",
        "backend_memory": "2Gi"
    },
    "results": {
        "http_reqs_total": 45000,
        "http_reqs_per_second": 75,
        "http_req_duration": {
            "avg": 85.3,
            "min": 12.1,
            "med": 72.1,
            "p90": 142.5,
            "p95": 156.8,
            "p99": 289.4,
            "max": 1245.6
        },
        "http_req_failed_rate": 0.0002,
        "checks_passed_rate": 0.998
    },
    "resources": {
        "cpu_avg_percent": 45,
        "cpu_max_percent": 78,
        "memory_avg_mb": 580,
        "memory_max_mb": 720,
        "db_connections_peak": 25,
        "db_connections_avg": 18
    },
    "thresholds_derived": {
        "p95_target_ms": 150,
        "p95_warning_ms": 200,
        "p99_critical_ms": 400,
        "error_rate_target": 0.001,
        "error_rate_critical": 0.01
    },
    "notes": "Initial baseline after v1.0 release"
}
```

### Step 5: Document in This File

Update the [Project-Specific Baselines](#project-specific-baselines) section below with your measured values.

---

## Project-Specific Baselines

> **Instructions**: Replace this section with your actual measured baselines after running tests.

### Current Baseline

**Baseline Date**: YYYY-MM-DD
**Git Commit**: _commit-hash_
**Environment**: Staging (describe hardware/cloud specs)
**Test Duration**: 10 minutes at 50 VUs

#### Endpoint Performance

| Endpoint | P50 | P95 | P99 | RPS | Notes |
|----------|-----|-----|-----|-----|-------|
| `GET /api/v1/health` | _Xms_ | _Xms_ | _Xms_ | _X_ | |
| `GET /api/v1/todos` | _Xms_ | _Xms_ | _Xms_ | _X_ | With N todos |
| `POST /api/v1/todos` | _Xms_ | _Xms_ | _Xms_ | _X_ | |

#### Aggregate Metrics

| Metric | Value |
|--------|-------|
| Total Requests | _X_ |
| Requests/Second | _X_ |
| Error Rate | _X%_ |
| Check Pass Rate | _X%_ |

#### Resource Usage

| Resource | Average | Peak |
|----------|---------|------|
| Backend CPU | _X%_ | _X%_ |
| Backend Memory | _XMB_ | _XMB_ |
| DB Connections | _X_ | _X_ |

---

## Performance Regression Detection

### Manual Detection Process

Compare new test results against baseline:

```bash
# Run current performance test
./scripts/load-test.sh load --vus 50 --duration 10m \
    --output results/current-$(date +%Y%m%d).json

# Compare with baseline
# Look for:
# - P95 regression > 10% from baseline
# - Error rate increase
# - Throughput decrease
```

### Automated Detection (CI)

Add to your CI pipeline:

```yaml
# .github/workflows/performance.yml
performance-test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Start services
      run: docker compose up -d

    - name: Wait for services
      run: ./scripts/wait-for-ready.sh

    - name: Run load test
      run: |
        ./scripts/load-test.sh load --vus 50 --duration 5m \
            --output results/ci-run.json

    - name: Check thresholds
      run: |
        # k6 will exit with non-zero if thresholds fail
        # Thresholds defined in k6.config.js
```

### Threshold Violation Response

When thresholds are violated:

```
1. IDENTIFY
   └── Which metrics violated thresholds?
   └── When did the regression start?
   └── What changed (commits, config, infra)?

2. INVESTIGATE
   └── Check recent commits for changes
   └── Review database query performance
   └── Check for N+1 queries
   └── Look for external service latency
   └── Review resource utilization

3. PROFILE
   └── Enable detailed profiling
   └── Use py-spy or similar for Python
   └── Check database slow query log
   └── Review trace data (if available)

4. RESOLVE
   └── Fix performance issue, OR
   └── Accept and update baseline (with justification)

5. DOCUMENT
   └── Record decision in baseline history
   └── Update monitoring if needed
```

### Baseline Update Policy

**Update baselines when:**

- New features fundamentally change performance characteristics
- Infrastructure changes affect baseline (more/less resources)
- After intentional optimizations (new, better baselines)
- After architecture changes

**DO NOT update baselines to:**

- Hide regressions
- Meet artificial deadlines
- Avoid investigation

**Baseline update process:**

1. Document reason for update
2. Get team agreement
3. Run full baseline measurement (3+ runs)
4. Update this document
5. Update monitoring thresholds
6. Commit changes with clear message

---

## Capacity Planning

### Scaling Factors

Based on load testing, estimate scaling needs:

| Concurrent Users | Expected RPS | Backend Replicas | Database | Redis |
|------------------|--------------|------------------|----------|-------|
| 100 | 10-50 | 1 | Shared | Shared |
| 500 | 50-200 | 2 | Dedicated small | Shared |
| 1,000 | 100-400 | 3 | Dedicated medium | Dedicated |
| 5,000 | 400-1000 | 5 | Dedicated large | Dedicated cluster |
| 10,000+ | 1000+ | 10+ | Primary + replicas | Redis cluster |

### Bottleneck Analysis

Common bottlenecks and solutions:

| Bottleneck | Symptoms | Solutions |
|------------|----------|-----------|
| **Database CPU** | High query time, slow aggregations | Query optimization, indexing, read replicas |
| **Database Connections** | Connection timeout, pool exhaustion | Increase pool size, connection pooling proxy (PgBouncer) |
| **Redis Memory** | Evictions, OOM | Increase instance size, implement cache eviction policy |
| **Backend CPU** | High latency under load | Horizontal scaling, code optimization |
| **Backend Memory** | OOM errors, swap usage | Memory profiling, increase limits, fix leaks |
| **Network** | Timeout errors, high latency | CDN, regional deployment, connection keep-alive |
| **External Services** | Keycloak latency | JWKS caching, local token validation |

### Load Testing for Capacity

To determine capacity limits:

```bash
# Run stress test
./scripts/load-test.sh stress

# Observe and note:
# - VU count when error rate exceeds 1%
# - VU count when P95 latency exceeds SLA
# - VU count when CPU/memory exceeds 85%
# - System recovery time after overload
```

### Capacity Planning Formula

```
Required Replicas = (Peak RPS * Safety Factor) / (RPS per Instance)

Where:
- Peak RPS = Expected peak requests per second
- Safety Factor = 1.5 to 2.0 (50-100% headroom)
- RPS per Instance = From baseline testing

Example:
- Expected peak: 500 RPS
- Safety factor: 1.5
- Baseline RPS per instance: 100
- Required replicas = (500 * 1.5) / 100 = 7.5 -> 8 replicas
```

---

## Alerting Thresholds

Based on baselines, configure monitoring alerts:

### Response Time Alerts


```yaml
# prometheus/alerts/performance.yml
groups:
  - name: performance
    rules:
      - alert: HighP95Latency
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket{job="backend"}[5m])) by (le)
          ) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P95 latency above 500ms"
          description: "95th percentile latency is {{ $value | humanizeDuration }} (threshold: 500ms)"

      - alert: CriticalP99Latency
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket{job="backend"}[5m])) by (le)
          ) > 1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "P99 latency above 1s"
          description: "99th percentile latency is {{ $value | humanizeDuration }} (threshold: 1s)"
```

### Error Rate Alerts

```yaml
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{job="backend",status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total{job="backend"}[5m]))
          > 0.01
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Error rate above 1%"
          description: "Server error rate is {{ $value | humanizePercentage }}"

      - alert: CriticalErrorRate
        expr: |
          sum(rate(http_requests_total{job="backend",status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total{job="backend"}[5m]))
          > 0.05
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Error rate above 5%"
          description: "Server error rate is {{ $value | humanizePercentage }}"
```

### Resource Alerts

```yaml
      - alert: HighCPUUsage
        expr: |
          avg(rate(container_cpu_usage_seconds_total{container="backend"}[5m])) * 100 > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Backend CPU usage above 85%"

      - alert: HighMemoryUsage
        expr: |
          container_memory_usage_bytes{container="backend"}
          /
          container_spec_memory_limit_bytes{container="backend"}
          * 100 > 90
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Backend memory usage above 90%"
```


---

## Baseline History

Track baseline evolution over time:

| Date | Git Commit | P95 (ms) | RPS | Error Rate | Notes |
|------|------------|----------|-----|------------|-------|
| _YYYY-MM-DD_ | _abc123_ | _150_ | _75_ | _0.02%_ | Initial baseline |
| | | | | | |

### Change Log

| Date | Change | Impact |
|------|--------|--------|
| _YYYY-MM-DD_ | _Description of change_ | _How it affected baselines_ |

---

## Related Documentation

- [Performance Testing Guide](./performance-testing-guide.md) - How to run and interpret tests
- [Load Testing README](../../tests/load/README.md) - k6 test details
- [Prometheus Alerting](../../observability/prometheus/alerts/) - Alert configuration
- [Capacity Planning](./capacity-planning.md) - Detailed scaling guidance (when available)
- [Incident Response Runbook](../runbooks/) - What to do when alerts fire

---

## Appendix: Metric Definitions

### k6 Metrics Reference

| Metric | Type | Description |
|--------|------|-------------|
| `http_reqs` | Counter | Total HTTP requests made |
| `http_req_duration` | Trend | Time for the complete request (send + wait + receive) |
| `http_req_blocked` | Trend | Time spent blocked before initiating request |
| `http_req_connecting` | Trend | Time spent establishing TCP connection |
| `http_req_waiting` | Trend | Time spent waiting for response (TTFB) |
| `http_req_failed` | Rate | Rate of failed requests |
| `iteration_duration` | Trend | Time for one complete script iteration |
| `vus` | Gauge | Current number of active virtual users |
| `checks` | Rate | Rate of successful checks |

### Percentile Definitions

| Percentile | Meaning |
|------------|---------|
| P50 (median) | 50% of requests faster than this |
| P90 | 90% of requests faster than this |
| P95 | 95% of requests faster than this |
| P99 | 99% of requests faster than this |
| P99.9 | 99.9% of requests faster than this |

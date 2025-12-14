# Observability Stack

This directory contains the configuration for Knowledge Mapper's complete observability stack including metrics collection, log aggregation, and distributed tracing.

## Overview

The observability stack follows a "fail-open" pattern: the backend application does NOT depend on observability services and will continue to function normally when they are unavailable. This ensures reliability while providing comprehensive monitoring capabilities.

**Architecture:**
```
+------------------+     +-----------------+     +------------------+
|     Backend      | --> |   Prometheus    | <-- |     Grafana      |
|  /metrics (8000) |     |     (9090)      |     |      (3000)      |
+------------------+     +-----------------+     +------------------+
         |                       |                       ^
         v                       v                       |
+------------------+     +-----------------+             |
|      Tempo       | <---|      Loki       | <-----------+
|  OTLP (4317/18)  |     |     (3100)      |
+------------------+     +-----------------+
                               ^
                               |
                        +-----------------+
                        |    Promtail     |
                        | (Docker socket) |
                        +-----------------+
```

## Components

### 1. Grafana (Port 3000)

Unified visualization platform for metrics, logs, and traces.

| Property | Value |
|----------|-------|
| **URL** | http://localhost:3000 |
| **Version** | 12.4.0 |
| **Auth** | Anonymous access enabled (development only) |

**Features:**
- Pre-configured datasources (Prometheus, Loki, Tempo)
- Dashboards-as-code provisioning
- Trace-to-logs correlation
- Log-to-trace correlation

### 2. Prometheus (Port 9090)

Metrics collection and time-series database.

| Property | Value |
|----------|-------|
| **URL** | http://localhost:9090 |
| **Version** | v3.4.1 |
| **Scrape Interval** | 15 seconds (5s for backend) |

**Features:**
- Automatic service discovery via Docker
- Scrapes metrics from backend, Keycloak, and observability services
- PromQL query language
- Alerting rule support

### 3. Loki (Port 3100)

Log aggregation and storage system.

| Property | Value |
|----------|-------|
| **URL** | http://localhost:3100 |
| **Version** | 3.6.2 |
| **Query Language** | LogQL |

**Features:**
- Efficient log storage with label-based indexing
- LogQL for powerful log queries
- Integrated with Grafana for visualization
- Log correlation with traces via trace IDs

### 4. Promtail

Log collection agent for Docker containers.

| Property | Value |
|----------|-------|
| **Version** | 3.6.2 |
| **Collection Method** | Docker socket |

**Features:**
- Automatic container discovery
- Docker metadata label enrichment
- Ships logs to Loki
- Structured log parsing support

**Security Note:** Promtail requires Docker socket access, which provides root-equivalent permissions. Ensure proper access controls in production.

### 5. Tempo (Ports 3200, 4317, 4318)

Distributed tracing backend.

| Property | Value |
|----------|-------|
| **HTTP API** | http://localhost:3200 |
| **OTLP gRPC** | localhost:4317 |
| **OTLP HTTP** | localhost:4318 |
| **Version** | 2.9.0 |

**Features:**
- OpenTelemetry Protocol (OTLP) support
- Trace storage and retrieval
- TraceQL query language
- Trace correlation with logs and metrics

## Quick Start

### Starting the Observability Stack

```bash
# Start all services (including observability)
docker compose up -d

# Or start only observability services
docker compose up -d prometheus loki promtail tempo grafana
```

### Verifying Services

```bash
# Check all services are running
docker compose ps

# Verify Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].health'

# Verify Loki is ready
curl -s http://localhost:3100/ready

# Verify Tempo is ready
curl -s http://localhost:3200/ready

# Verify Grafana is healthy
curl -s http://localhost:3000/api/health
```

### Accessing Services

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Dashboards and exploration |
| Prometheus | http://localhost:9090 | Direct metrics queries |
| Loki | http://localhost:3100 | Log API (use Grafana for UI) |
| Tempo | http://localhost:3200 | Trace API (use Grafana for UI) |
| Backend Metrics | http://localhost:8000/metrics | Raw Prometheus metrics |

## Common Tasks

### Viewing Logs

In Grafana (http://localhost:3000):

1. Navigate to **Explore**
2. Select **Loki** datasource
3. Use LogQL queries:

```logql
# All logs from backend
{container="knowledge-mapper-backend"}

# Error logs only
{container="knowledge-mapper-backend"} |= "ERROR"

# Logs with specific trace ID
{container="knowledge-mapper-backend"} | json | trace_id="<trace-id>"

# Keycloak logs
{container="knowledge-mapper-keycloak"}

# Filter by log level (if using structured logging)
{container="knowledge-mapper-backend"} | json | level="error"
```

### Viewing Traces

In Grafana (http://localhost:3000):

1. Navigate to **Explore**
2. Select **Tempo** datasource
3. Use TraceQL or search:

```traceql
# Find traces by service name
{resource.service.name="knowledge-mapper-backend"}

# Find traces with errors
{status=error}

# Find slow traces (> 1 second)
{duration > 1s}

# Find traces by HTTP endpoint
{span.http.route="/api/v1/health"}
```

**Trace-to-Logs:**
- Click on any span
- Select "Logs for this span" to jump to related logs

### Viewing Metrics

In Grafana (http://localhost:3000):

1. Navigate to **Dashboards** for pre-built views, or
2. Navigate to **Explore** with **Prometheus** datasource

**Example PromQL Queries:**

```promql
# Request rate by endpoint
rate(http_requests_total{job="backend"}[5m])

# 95th percentile latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="backend"}[5m]))

# Error rate (5xx responses)
rate(http_requests_total{job="backend",status=~"5.."}[5m])

# Active requests
http_requests_active{job="backend"}

# CPU usage by container
rate(container_cpu_usage_seconds_total[5m])
```

### Creating Custom Dashboards

1. Go to **Dashboards** > **New Dashboard**
2. Add panels with queries for your metrics
3. Export as JSON via **Dashboard settings** > **JSON Model**
4. Save to `observability/grafana/dashboards/` for version control

## Configuration Files

| File | Purpose |
|------|---------|
| `prometheus/prometheus.yml` | Scrape targets and intervals |
| `loki/loki-config.yml` | Log storage and retention settings |
| `promtail/promtail-config.yml` | Docker log collection rules |
| `tempo/tempo.yml` | Trace storage and protocol settings |
| `grafana/datasources/datasources.yml` | Pre-configured data source connections |
| `grafana/dashboards/dashboards.yml` | Dashboard provisioning configuration |
| `grafana/dashboards/*.json` | Dashboard definitions (dashboards-as-code) |

### Configuration Highlights

**Prometheus (`prometheus/prometheus.yml`):**
- Scrape interval: 15 seconds (global), 5 seconds (backend)
- Targets: backend, prometheus, loki, tempo, grafana

**Loki (`loki/loki-config.yml`):**
- Storage: Local filesystem
- Retention: Configurable via schema

**Tempo (`tempo/tempo.yml`):**
- Receivers: OTLP gRPC and HTTP
- Storage: Local filesystem
- Block retention: Development-appropriate settings

## Data Retention

Current development configuration:

| Service | Retention | Notes |
|---------|-----------|-------|
| Prometheus | Storage-based | Limited by disk capacity |
| Loki | Schema-based | See `loki-config.yml` |
| Tempo | 1-hour blocks | Suitable for development |
| Grafana | N/A | Dashboards stored as files |

**Production Recommendation:** Adjust retention policies in respective configuration files based on storage capacity and compliance requirements.

## Troubleshooting

### Logs Not Appearing in Loki

1. **Check Promtail status:**
   ```bash
   docker compose ps promtail
   docker compose logs promtail
   ```

2. **Verify Docker socket access:**
   ```bash
   docker compose exec promtail ls -la /var/run/docker.sock
   ```

3. **Check Loki is receiving data:**
   ```bash
   curl -s "http://localhost:3100/loki/api/v1/labels" | jq
   ```

4. **Verify container logs exist:**
   ```bash
   ls -la /var/lib/docker/containers/
   ```

### Traces Not Appearing in Tempo

1. **Verify OTLP endpoint configuration:**
   - Backend should export to `http://tempo:4317` (gRPC) or `http://tempo:4318` (HTTP)

2. **Check Tempo logs:**
   ```bash
   docker compose logs tempo
   ```

3. **Verify Tempo is ready:**
   ```bash
   curl -s http://localhost:3200/ready
   ```

4. **Test OTLP endpoint:**
   ```bash
   # Check if Tempo is accepting traces
   curl -v http://localhost:4318/v1/traces
   ```

### Metrics Not Being Scraped

1. **Check Prometheus targets:**
   - Visit http://localhost:9090/targets
   - Look for targets marked as "DOWN"

2. **Verify service metrics endpoint:**
   ```bash
   curl -s http://localhost:8000/metrics | head -20
   ```

3. **Check Prometheus configuration:**
   ```bash
   docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
   ```

4. **Review Prometheus logs:**
   ```bash
   docker compose logs prometheus
   ```

### Grafana Issues

1. **Datasource connection errors:**
   - Verify all observability services are running
   - Check service names match in datasource configuration

2. **Dashboard not loading:**
   ```bash
   docker compose logs grafana
   ```

3. **Reset Grafana state:**
   ```bash
   docker compose down grafana
   docker volume rm knowledge-mapper-grafana-data
   docker compose up -d grafana
   ```

### Common Network Issues

1. **Services cannot communicate:**
   ```bash
   # Verify network exists
   docker network ls | grep knowledge-mapper

   # Check service connectivity
   docker compose exec prometheus wget -q -O- http://loki:3100/ready
   ```

2. **Port conflicts:**
   - Check if ports are available: `lsof -i :3000`
   - Modify port mappings in `compose.yml` or `.env` if needed

## Security Notes

**WARNING: Development Configuration**

The current setup has security features disabled for development convenience:

| Setting | Current | Production Recommendation |
|---------|---------|---------------------------|
| Grafana Auth | Anonymous Admin | Enable authentication |
| Prometheus Auth | None | Add basic auth or OAuth proxy |
| Loki Auth | None | Enable authentication |
| Tempo Auth | None | Enable authentication |
| TLS | Disabled | Enable for all services |
| Network | Bridge (exposed) | Internal network with reverse proxy |

**Production Checklist:**

1. [ ] Enable Grafana authentication (LDAP/OAuth/built-in)
2. [ ] Add authentication proxy for Prometheus/Loki/Tempo
3. [ ] Enable TLS for all service communications
4. [ ] Configure proper network segmentation
5. [ ] Set appropriate data retention policies
6. [ ] Implement backup strategies
7. [ ] Remove Docker socket access if not needed
8. [ ] Configure alerting and on-call rotation

## Resource Limits

Resource constraints are commented out in `compose.yml`. For production or resource-constrained environments, uncomment and adjust:

```yaml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '0.5'
    reservations:
      memory: 256M
```

## Related Documentation

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Loki Documentation](https://grafana.com/docs/loki/)
- [Tempo Documentation](https://grafana.com/docs/tempo/)
- [Grafana Documentation](https://grafana.com/docs/grafana/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)

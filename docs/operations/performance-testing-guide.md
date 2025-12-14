# Performance Testing Guide

This guide explains how to run performance tests and interpret results for Knowledge Mapper.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Test Scenarios](#test-scenarios)
- [Running Tests](#running-tests)
- [Interpreting Results](#interpreting-results)
- [Understanding k6 Output](#understanding-k6-output)
- [Custom Tests](#custom-tests)
- [Authenticated Testing](#authenticated-testing)
- [CI Integration](#ci-integration)
- [Troubleshooting](#troubleshooting)
- [Related Documentation](#related-documentation)

---

## Prerequisites

### Install k6

**macOS:**
```bash
brew install k6
```

**Ubuntu/Debian:**
```bash
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
    --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | \
    sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

**Windows:**
```bash
winget install k6 --source winget
# or
choco install k6
```

**Docker (no installation):**
```bash
docker run --rm -i grafana/k6 run -
```

**Verify installation:**
```bash
k6 version
# Expected: k6 v0.47.0 or higher
```

### Start the Application

```bash
# Start all services
./scripts/docker-dev.sh up

# Wait for services to be ready
./scripts/docker-dev.sh logs backend  # Check for "Application startup complete"

# Verify health endpoint
curl http://localhost:8000/api/v1/health
```

---

## Quick Start

### Run Your First Test

```bash
# Quick validation (smoke test)
./scripts/load-test.sh smoke
```

**Expected output:**
```
     checks.........................: 100.00%
     http_req_duration..............: avg=45ms  p(95)=89ms
     http_req_failed................: 0.00%
```

### Common Commands

```bash
# Smoke test - Quick validation
./scripts/load-test.sh smoke

# Load test - Normal traffic
./scripts/load-test.sh load

# Stress test - Find breaking points
./scripts/load-test.sh stress

# Soak test - Extended reliability
./scripts/load-test.sh soak

# Custom options
./scripts/load-test.sh load --vus 100 --duration 15m

# Save results
./scripts/load-test.sh load --output results.json
```

---

## Test Scenarios

### Scenario Overview

| Scenario | Purpose | VUs | Duration | Use Case |
|----------|---------|-----|----------|----------|
| **Smoke** | Quick validation | 1 | 1 min | Pre-deployment check |
| **Load** | Normal expected load | 50 | 5 min | Performance validation |
| **Stress** | Find breaking points | 10-200 | 25 min | Capacity planning |
| **Soak** | Extended reliability | 20 | 30 min | Memory leak detection |

### Smoke Test

**Purpose**: Verify the system is functional before running heavier tests.

```bash
./scripts/load-test.sh smoke
```

**Configuration**:
- Virtual Users: 1
- Duration: 1 minute
- Iterations: ~60

**Pass Criteria**:
- All checks pass (100%)
- No failed requests (0%)
- P95 latency < 500ms

**When to use**:
- Before deployments
- After infrastructure changes
- As part of CI pipeline
- Before longer performance tests

### Load Test

**Purpose**: Validate performance under normal expected traffic patterns.

```bash
./scripts/load-test.sh load
./scripts/load-test.sh load --vus 100        # Higher load
./scripts/load-test.sh load --duration 15m   # Longer duration
```

**Configuration**:
- Virtual Users: 50 (default)
- Duration: 5 minutes (default)
- Ramp-up: 30 seconds

**Pass Criteria**:
- Checks > 95%
- Error rate < 1%
- P95 latency < 500ms
- Throughput > 50 RPS

**When to use**:
- Establishing baselines
- Validating SLA compliance
- Regression testing
- Release validation

### Stress Test

**Purpose**: Find system limits and observe behavior under extreme load.

```bash
./scripts/load-test.sh stress
```

**Configuration**:
- Stages:
  1. Ramp to 50 VUs (2 min)
  2. Hold at 50 VUs (5 min)
  3. Ramp to 100 VUs (2 min)
  4. Hold at 100 VUs (5 min)
  5. Ramp to 200 VUs (2 min)
  6. Hold at 200 VUs (5 min)
  7. Ramp down (2 min)
- Total Duration: ~25 minutes

**What to observe**:
- At what VU count does error rate spike?
- At what VU count does latency exceed SLA?
- Does the system recover after load decreases?
- What are the resource limits (CPU, memory)?

**Pass Criteria** (more lenient):
- Error rate < 10%
- P95 latency < 2000ms
- System recovers after peak

### Soak Test

**Purpose**: Find memory leaks, connection leaks, and resource exhaustion over time.

```bash
./scripts/load-test.sh soak
./scripts/load-test.sh soak --duration 2h   # Extended soak test
```

**Configuration**:
- Virtual Users: 20
- Duration: 30 minutes (default)
- Constant load throughout

**What to observe**:
- Memory growth over time
- Response time degradation
- Connection pool exhaustion
- Database connection leaks
- Log file growth

**Pass Criteria**:
- No memory leaks (< 10% growth over duration)
- Latency stable (< 20% variation)
- Error rate stable (no increase over time)

---

## Running Tests

### Command Line Options

```bash
./scripts/load-test.sh <scenario> [options]

Scenarios:
  smoke       Quick validation (1 VU, 1 min)
  load        Normal load test (50 VUs, 5 min)
  stress      Progressive stress test (~25 min)
  soak        Extended duration test (30 min)

Options:
  --vus N        Override virtual users count
  --duration T   Override duration (e.g., 5m, 1h)
  --base-url U   Override API base URL
  --output F     Save results to JSON file
  --json         Save results with timestamp
  --quiet        Suppress k6 progress output
  --help         Show help
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BASE_URL` | API base URL | `http://localhost:8000` |
| `VUS` | Virtual users | Scenario-specific |
| `DURATION` | Test duration | Scenario-specific |
| `ENVIRONMENT` | Environment tag | `local` |
| `ACCESS_TOKEN` | Auth token | None |

### Running with Docker

If k6 is not installed locally:

```bash
# Run smoke test
docker run --rm -i --network host \
    -v $(pwd)/tests/load:/tests \
    grafana/k6 run /tests/scenarios/smoke.js

# Run with environment variables
docker run --rm -i --network host \
    -v $(pwd)/tests/load:/tests \
    -e BASE_URL=http://localhost:8000 \
    grafana/k6 run /tests/scenarios/load.js

# Save results
docker run --rm -i --network host \
    -v $(pwd)/tests/load:/tests \
    -v $(pwd)/results:/results \
    grafana/k6 run /tests/scenarios/load.js \
    --out json=/results/output.json
```

---

## Interpreting Results

### Understanding k6 Output

After each test, k6 outputs a summary:

```
     checks.........................: 100.00% 60 out of 60
     data_received..................: 123 kB  2.0 kB/s
     data_sent......................: 5.4 kB  89 B/s
     http_req_blocked...............: avg=1.2ms   min=1us    max=45ms    p(90)=1ms    p(95)=5ms
     http_req_connecting............: avg=0.8ms   min=0s     max=35ms    p(90)=0s     p(95)=2ms
     http_req_duration..............: avg=85.3ms  min=12ms   med=72ms    max=1245ms   p(90)=145ms  p(95)=156ms
       { expected_response:true }...: avg=84.1ms  min=12ms   med=71ms    max=1102ms   p(90)=142ms  p(95)=153ms
     http_req_failed................: 0.02%   1 out of 45000
     http_req_receiving.............: avg=0.5ms   min=0s     med=0s      max=45ms     p(90)=1ms    p(95)=2ms
     http_req_sending...............: avg=0.1ms   min=0s     med=0s      max=12ms     p(90)=0s     p(95)=0s
     http_req_tls_handshaking.......: avg=0s      min=0s     med=0s      max=0s       p(90)=0s     p(95)=0s
     http_req_waiting...............: avg=84.7ms  min=11ms   med=71ms    max=1200ms   p(90)=143ms  p(95)=154ms
     http_reqs......................: 45000   750/s
     iteration_duration.............: avg=2.1s    min=1.5s   med=2s      max=5.2s     p(90)=2.8s   p(95)=3.1s
     iterations.....................: 22500   375/s
     vus............................: 50      min=0       max=50
     vus_max........................: 50      min=50      max=50
```

### Key Metrics Explained

| Metric | Description | Target Value | Notes |
|--------|-------------|--------------|-------|
| `checks` | Assertion pass rate | > 95% | Custom validations defined in tests |
| `http_req_duration` | Total request time | P95 < 500ms | Key latency metric |
| `http_req_failed` | Error percentage | < 1% | 4xx/5xx responses |
| `http_reqs` | Requests per second | > 50 | Throughput indicator |
| `http_req_blocked` | Time waiting for free connection | < 10ms avg | Connection pool indicator |
| `http_req_waiting` | Server processing time | Close to duration | Network vs server time |
| `iteration_duration` | Full script iteration time | Depends on script | Includes think time |
| `vus` | Virtual users | As configured | Concurrent connections |

### Metric Breakdowns

**http_req_duration breakdown:**

```
Total request time = blocked + connecting + sending + waiting + receiving

Where:
- blocked: Waiting for free connection from pool
- connecting: TCP connection establishment
- sending: Sending request data
- waiting: Waiting for first byte (TTFB)
- receiving: Receiving response data
```

**Interpreting percentiles:**

```
avg  = Average (can be misleading with outliers)
med  = Median (50th percentile) - typical request
p90  = 90% of requests are faster than this
p95  = 95% of requests are faster than this (common SLA metric)
p99  = 99% of requests are faster than this (outlier indicator)
max  = Slowest request (often an outlier)
```

### Success Criteria by Scenario

| Scenario | Checks | Error Rate | P95 Latency | Notes |
|----------|--------|------------|-------------|-------|
| Smoke | 100% | 0% | < 500ms | Any failure = fail |
| Load | > 95% | < 1% | < 500ms | Standard thresholds |
| Stress | > 90% | < 10% | < 2000ms | Expect degradation |
| Soak | > 95% | < 1% | Stable | No degradation over time |

---

## Understanding k6 Output

### Identifying Issues

#### High Latency (P95 > 500ms)

**Symptoms:**
```
http_req_duration..............: avg=450ms  p(95)=890ms  p(99)=1.5s
```

**Investigation steps:**
1. Check `http_req_waiting` vs total duration (server vs network)
2. Check database query performance
3. Look for N+1 query patterns in logs
4. Check external service calls (Keycloak)
5. Review connection pool settings

**Common causes:**
- Slow database queries
- Missing database indexes
- External service latency
- Connection pool exhaustion
- CPU-bound operations

#### High Error Rate (> 1%)

**Symptoms:**
```
http_req_failed................: 5.23%  2500 out of 47800
```

**Investigation steps:**
1. Check application logs for error details
2. Review rate limiting settings
3. Check database connection limits
4. Look for resource exhaustion

**Common causes:**
- Rate limiting triggered
- Database connection exhaustion
- Memory exhaustion (OOM)
- Validation errors
- Auth token expiration

#### Low Throughput (< expected RPS)

**Symptoms:**
```
http_reqs......................: 15000   25/s  # Expected: 100+/s
```

**Investigation steps:**
1. Check if VUs are waiting (high think time)
2. Review connection limits
3. Check for synchronous bottlenecks
4. Verify test script isn't self-throttling

**Common causes:**
- Think time too high in test script
- Connection pool limits
- Single-threaded bottleneck
- External dependency slow

#### High Blocked Time

**Symptoms:**
```
http_req_blocked...............: avg=150ms  max=3s
```

**Investigation steps:**
1. Check connection pool size
2. Review keep-alive settings
3. Check for connection leaks

**Common causes:**
- Connection pool exhaustion
- Too many concurrent requests
- Connection not being reused

### Reading Threshold Results

```
     http_req_duration..............: avg=85.3ms  p(95)=156ms
       { expected_response:true }...: avg=84.1ms  p(95)=153ms

     ??? http_req_duration............: p(95)<500ms  ??? pass
     ??? http_req_failed..............: rate<0.01    ??? pass
     ??? checks.......................: rate>0.95    ??? pass
```

- `???` = Threshold passed
- `???` = Threshold failed (test fails)

---

## Custom Tests

### Creating Custom Test Scripts

Create new tests in `tests/load/scripts/`:

```javascript
// tests/load/scripts/my-endpoint.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, API_PREFIX } from '../lib/config.js';

export const options = {
    vus: 10,
    duration: '5m',
    thresholds: {
        http_req_duration: ['p(95)<500'],
        http_req_failed: ['rate<0.01'],
        checks: ['rate>0.95'],
    },
};

export default function() {
    // Make request
    const response = http.get(`${BASE_URL}${API_PREFIX}/my-endpoint`);

    // Validate response
    check(response, {
        'status is 200': (r) => r.status === 200,
        'response time < 200ms': (r) => r.timings.duration < 200,
        'has expected field': (r) => JSON.parse(r.body).hasOwnProperty('id'),
    });

    // Think time between requests
    sleep(1);
}
```

Run with:
```bash
k6 run tests/load/scripts/my-endpoint.js
```

### Using Shared Libraries

```javascript
// Import shared configuration
import { BASE_URL, API_PREFIX, authHeaders } from '../lib/config.js';

// Import common checks
import { checkApiResponse, checkHealthResponse } from '../lib/checks.js';

// Import helpers
import { thinkTime, generateTestId, randomItem } from '../lib/helpers.js';
```

### Parameterized Tests

```javascript
import http from 'k6/http';
import { check } from 'k6';

// Read test data
const testData = JSON.parse(open('./data/users.json'));

export default function() {
    // Select random test user
    const user = testData[Math.floor(Math.random() * testData.length)];

    const response = http.get(`${BASE_URL}/api/v1/users/${user.id}`);

    check(response, {
        'status is 200': (r) => r.status === 200,
        'correct user': (r) => JSON.parse(r.body).id === user.id,
    });
}
```

### Staged Tests

```javascript
export const options = {
    stages: [
        { duration: '2m', target: 10 },   // Ramp up to 10 VUs
        { duration: '5m', target: 10 },   // Stay at 10 VUs
        { duration: '2m', target: 50 },   // Ramp up to 50 VUs
        { duration: '5m', target: 50 },   // Stay at 50 VUs
        { duration: '2m', target: 0 },    // Ramp down
    ],
};
```

---

## Authenticated Testing

### With Pre-Generated Token

```bash
# Get a token
TOKEN=$(curl -s -X POST http://localhost:8080/realms/knowledge-mapper-dev/protocol/openid-connect/token \
    -d "grant_type=password" \
    -d "client_id=knowledge-mapper-app" \
    -d "username=alice@example.com" \
    -d "password=password123" | jq -r '.access_token')

# Run test with token
k6 run --env ACCESS_TOKEN=$TOKEN tests/load/scripts/api-authenticated.js
```

### With Test Users

```bash
# Configure test users
export TEST_USERS="alice@example.com:password123,bob@example.com:password123"
export TOKEN_URL="http://localhost:8080/realms/knowledge-mapper-dev/protocol/openid-connect/token"
export CLIENT_ID="knowledge-mapper-app"

# Run authenticated tests
./scripts/load-test.sh api-auth
```

### Token Management

The test framework includes automatic token management:

```javascript
import { getToken, authHeaders, getValidToken } from '../lib/auth.js';

export default function() {
    // Get headers with valid token
    const headers = authHeaders(__VU);  // VU index for round-robin

    // Make authenticated request
    const response = http.get(`${BASE_URL}/api/v1/protected`, { headers });

    check(response, {
        'authenticated': (r) => r.status !== 401,
    });
}
```

---

## CI Integration

### GitHub Actions Example

```yaml
# .github/workflows/performance.yml
name: Performance Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  performance:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Start services
        run: docker compose up -d

      - name: Wait for services
        run: |
          timeout 120 bash -c 'until curl -f http://localhost:8000/api/v1/health; do sleep 2; done'

      - name: Install k6
        run: |
          sudo gpg -k
          sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
              --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
          echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | \
              sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update && sudo apt-get install k6

      - name: Run smoke test
        run: ./scripts/load-test.sh smoke

      - name: Run load test
        run: ./scripts/load-test.sh load --vus 20 --duration 2m

      - name: Upload results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: k6-results
          path: tests/load/results/

      - name: Stop services
        if: always()
        run: docker compose down
```

### Threshold-Based CI Failures

k6 exits with non-zero code if thresholds fail:

```javascript
// k6.config.js
export const options = {
    thresholds: {
        http_req_duration: ['p(95)<500'],  // Fails if P95 > 500ms
        http_req_failed: ['rate<0.01'],    // Fails if error rate > 1%
        checks: ['rate>0.95'],             // Fails if checks < 95%
    },
};
```

---

## Troubleshooting

### "Connection refused" Errors

```bash
# Check if backend is running
curl http://localhost:8000/api/v1/health

# Check Docker containers
docker compose ps

# Check backend logs
docker compose logs backend
```

### High Error Rate from Start

```bash
# Check backend logs for errors
docker compose logs backend --tail 100

# Check database connectivity
docker compose exec backend python -c "from app.core.database import engine; print('DB OK')"

# Check Redis connectivity
docker compose exec redis redis-cli ping
```

### Results Vary Significantly Between Runs

**Causes:**
- Other processes using resources
- Container resource limits
- Garbage collection
- Test duration too short

**Solutions:**
1. Ensure no other load on system
2. Run from consistent environment
3. Use longer test durations (10+ minutes)
4. Run multiple times and average results
5. Check for background processes:
   ```bash
   docker stats  # Monitor container resources
   ```

### k6 Not Found

```bash
# Use Docker instead
docker run --rm -i --network host \
    -v $(pwd)/tests/load:/tests \
    grafana/k6 run /tests/scenarios/smoke.js
```

### Out of Memory

```bash
# Increase container memory limits in compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 4G

# Or reduce VUs
./scripts/load-test.sh load --vus 20
```

### Keycloak Token Errors

```bash
# Verify Keycloak is running
curl http://localhost:8080

# Test token endpoint manually
curl -X POST http://localhost:8080/realms/knowledge-mapper-dev/protocol/openid-connect/token \
    -d "grant_type=password" \
    -d "client_id=knowledge-mapper-app" \
    -d "username=alice@example.com" \
    -d "password=password123"
```

---

## Related Documentation

- [Performance Baselines](./performance-baselines.md) - KPIs and baseline measurements
- [Load Testing README](../../tests/load/README.md) - Detailed k6 configuration
- [k6 Documentation](https://k6.io/docs/) - Official k6 docs
- [k6 Extensions](https://k6.io/docs/extensions/) - Additional functionality
- [Grafana Dashboards](../../observability/grafana/) - Visualize test results

---

## Appendix: Test Data Setup

### Creating Test Users

```bash
# Access Keycloak admin console
open http://localhost:8080/admin
# Login: admin / admin

# Or use setup script
./keycloak/setup-realm.sh
```

Default test users:
- `alice@example.com` (password: `password123`)
- `bob@example.com` (password: `password123`)

### Seeding Test Data

```bash
# Seed database with test data
docker compose exec backend python scripts/seed_data.py

# Or manually via API
for i in {1..100}; do
    curl -X POST http://localhost:8000/api/v1/todos \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"Todo $i\", \"completed\": false}"
done
```

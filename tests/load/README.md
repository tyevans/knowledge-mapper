# Load Testing

This directory contains k6 load testing scripts for Knowledge Mapper.

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

**Docker:**
```bash
docker run --rm -i grafana/k6 run -
```

**Windows:**
```bash
winget install k6 --source winget
# or
choco install k6
```

For more installation options, see: https://k6.io/docs/get-started/installation/

## Quick Start

```bash
# Run smoke test (quick validation)
./scripts/load-test.sh smoke

# Run load test (normal traffic)
./scripts/load-test.sh load

# Run with custom options
./scripts/load-test.sh load --vus 100 --duration 10m

# Test against staging
./scripts/load-test.sh smoke --base-url https://staging.example.com
```

## Test Scenarios

| Scenario | Description | VUs | Duration | Use Case |
|----------|-------------|-----|----------|----------|
| `smoke` | Quick validation | 1 | 1 minute | Pre-deployment check |
| `load` | Normal expected load | 50 | 5 minutes | Performance validation |
| `stress` | Find breaking points | Up to 200 | 25 minutes | Capacity planning |
| `soak` | Extended reliability | 20 | 30 minutes | Memory leak detection |

### Smoke Test

Minimal test to verify the system is responding. Run before other tests or deployments.

```bash
./scripts/load-test.sh smoke
```

**Purpose:**
- Verify endpoints are accessible
- Catch obvious configuration issues
- Quick validation (< 2 minutes)

### Load Test

Simulates normal expected traffic patterns. Use to validate performance meets SLAs.

```bash
./scripts/load-test.sh load
./scripts/load-test.sh load --vus 100        # Higher load
./scripts/load-test.sh load --duration 15m   # Longer duration
```

**Purpose:**
- Validate performance under normal conditions
- Establish baseline metrics
- Verify SLA compliance

### Stress Test

Progressively increases load to find system limits and breaking points.

```bash
./scripts/load-test.sh stress
```

**Purpose:**
- Find system capacity limits
- Observe behavior under extreme load
- Test recovery after overload

### Soak Test

Extended duration test to find memory leaks and resource exhaustion issues.

```bash
./scripts/load-test.sh soak
./scripts/load-test.sh soak --duration 2h   # 2-hour soak test
```

**Purpose:**
- Detect memory leaks
- Find resource exhaustion
- Validate long-term stability

## Directory Structure

```
tests/load/
  k6.config.js           # Shared configuration
  scenarios/             # Test scenarios
    smoke.js             # Quick validation
    load.js              # Normal load
    stress.js            # Breaking points
    soak.js              # Extended duration
  scripts/               # Endpoint-specific tests
    health.js            # Health endpoint
    api-public.js        # Public API endpoints
    api-authenticated.js # Authenticated endpoints
  lib/                   # Shared utilities
    config.js            # Configuration
    helpers.js           # Helper functions
    checks.js            # Common checks
  results/               # Test output (gitignored)
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BASE_URL` | API base URL | `http://localhost:8000` |
| `VUS` | Virtual users count | Scenario-specific |
| `DURATION` | Test duration | Scenario-specific |
| `ENVIRONMENT` | Environment tag | `local` |
| `ACCESS_TOKEN` | Auth token for authenticated tests | None |

### Command Line Options

```bash
./scripts/load-test.sh <scenario> [options]

Options:
  --vus N        Override virtual users
  --duration T   Override duration (e.g., 5m, 1h)
  --base-url U   Override base URL
  --output F     Save results to file
  --json         Save results as timestamped JSON
  --quiet        Suppress k6 progress output
  --help         Show help
```

### Running with Docker

If you prefer not to install k6 locally:

```bash
# Smoke test
docker run --rm -i --network host \
    -v $(pwd)/tests/load:/tests \
    grafana/k6 run /tests/scenarios/smoke.js

# With environment variables
docker run --rm -i --network host \
    -v $(pwd)/tests/load:/tests \
    -e BASE_URL=http://localhost:8000 \
    grafana/k6 run /tests/scenarios/load.js
```

## Thresholds

Default performance thresholds:

| Metric | Threshold | Description |
|--------|-----------|-------------|
| `http_req_duration` | p95 < 500ms | 95th percentile response time |
| `http_req_failed` | rate < 1% | Error rate |
| `checks` | rate > 95% | Check pass rate |

### Health Endpoint Thresholds

| Metric | Threshold |
|--------|-----------|
| `http_req_duration` | p95 < 100ms |
| `http_req_failed` | rate < 0.1% |

### Stress Test Thresholds (More Lenient)

| Metric | Threshold |
|--------|-----------|
| `http_req_duration` | p95 < 2000ms |
| `http_req_failed` | rate < 10% |

## Viewing Results

### Console Output

k6 outputs summary statistics after each run:

```
     checks.........................: 100.00% 60 out of 60
     data_received..................: 123 kB  2.0 kB/s
     data_sent......................: 5.4 kB  89 B/s
     http_req_blocked...............: avg=1.2ms   min=1us    max=45ms
     http_req_duration..............: avg=12.5ms  min=2ms    max=89ms
       { expected_response:true }...: avg=12.5ms  min=2ms    max=89ms
     http_reqs......................: 60      1/s
     iteration_duration.............: avg=1.02s   min=1.01s  max=1.08s
     iterations.....................: 60      1/s
```

### JSON Output

Save detailed results for analysis:

```bash
./scripts/load-test.sh load --output load-results.json
```

### Summary Files

Each scenario generates a summary JSON file in the `results/` directory:
- `results/smoke-test-summary.json`
- `results/load-test-summary.json`
- `results/stress-test-summary.json`
- `results/soak-test-summary.json`

### Grafana Dashboard (Optional)

With InfluxDB enabled, stream results to Grafana:

```bash
k6 run --out influxdb=http://localhost:8086/k6 tests/load/scenarios/load.js
```


With the observability stack, you can correlate load test metrics with application metrics in Grafana.


## Writing Custom Tests

Create new test files in `scripts/` or `scenarios/`:

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, API_PREFIX } from '../lib/config.js';

export const options = {
  vus: 10,
  duration: '5m',
  thresholds: {
    http_req_duration: ['p(95)<500'],
  },
};

export default function() {
  const response = http.get(`${BASE_URL}${API_PREFIX}/your-endpoint`);
  check(response, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(1);
}
```

### Using Shared Libraries

```javascript
import { BASE_URL, API_PREFIX, authHeaders } from '../lib/config.js';
import { checkApiResponse, checkHealthResponse } from '../lib/checks.js';
import { thinkTime, generateTestId } from '../lib/helpers.js';
```

## Authenticated Tests

For testing authenticated endpoints, see `scripts/api-authenticated.js`.

### With Pre-Generated Token

```bash
./scripts/load-test.sh api-auth --env ACCESS_TOKEN=your_jwt_token
```

### With Client Credentials

```bash
export CLIENT_ID=your-client-id
export CLIENT_SECRET=your-client-secret
export TOKEN_URL=http://localhost:8080/realms/knowledge-mapper-dev/protocol/openid-connect/token

./scripts/load-test.sh api-auth
```

## Troubleshooting

### Connection Refused

Ensure the backend is running:

```bash
./scripts/docker-dev.sh up
```

### High Error Rate

1. Check backend logs:
   ```bash
   docker compose logs backend
   ```

2. Reduce VU count:
   ```bash
   ./scripts/load-test.sh load --vus 10
   ```

3. Check resource limits:
   ```bash
   docker stats
   ```

### Slow Response Times

1. Check database connections:
   ```bash
   docker compose exec postgres psql -U knowledge_mapper_user -c "SELECT * FROM pg_stat_activity"
   ```

2. Monitor Redis:
   ```bash
   docker compose exec redis redis-cli info
   ```

3. Check for N+1 queries in backend logs

### k6 Not Found

Install k6 following the instructions above, or use Docker:

```bash
docker run --rm -i --network host -v $(pwd)/tests/load:/tests grafana/k6 run /tests/scenarios/smoke.js
```

## Performance Baselines

After running load tests, document your baselines:

| Endpoint | p50 | p95 | p99 | Max | Target |
|----------|-----|-----|-----|-----|--------|
| `/api/v1/health` | 5ms | 15ms | 25ms | 50ms | < 100ms |
| `/openapi.json` | 20ms | 50ms | 80ms | 150ms | < 500ms |

## CI Integration

For automated load testing in CI pipelines, see the GitHub Actions workflow examples in `.github/workflows/`.

Example CI job:

```yaml
load-test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Start services
      run: docker compose up -d

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
```

## Authenticated Testing

The load testing framework includes comprehensive authentication flow tests using OAuth 2.0 with Keycloak.

### Prerequisites

1. **Keycloak Running:**
   ```bash
   ./scripts/docker-dev.sh up
   ```

2. **Test Users Created:**
   The default test users are `alice@example.com` and `bob@example.com` (password: `password123`).

   To create additional test users:
   ```bash
   # Access Keycloak admin console
   open http://localhost:8080/admin
   # Login: admin / admin
   ```

3. **OAuth Client Configured:**
   The client should allow "Direct Access Grants" (password grant) for load testing.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TOKEN_URL` | OAuth token endpoint | `http://localhost:8080/realms/knowledge-mapper-dev/protocol/openid-connect/token` |
| `CLIENT_ID` | OAuth client ID | `knowledge-mapper-app` |
| `CLIENT_SECRET` | Client secret (optional) | None |
| `TEST_USERS` | Comma-separated user:pass pairs | `alice@example.com:password123,bob@example.com:password123` |
| `ACCESS_TOKEN` | Pre-provided JWT (bypasses user login) | None |
| `AUTH_DEBUG` | Enable debug logging | `false` |
| `TOKEN_REFRESH_THRESHOLD` | Seconds before expiry to refresh | `60` |

### Running Authenticated Tests

```bash
# Run authenticated API tests with default users
./scripts/load-test.sh api-auth

# Run with custom test users
k6 run --env TEST_USERS=user1:pass1,user2:pass2 tests/load/scripts/api-authenticated.js

# Run with pre-provided token
k6 run --env ACCESS_TOKEN=eyJ... tests/load/scripts/api-authenticated.js

# Run with debug logging
k6 run --env AUTH_DEBUG=true tests/load/scripts/api-authenticated.js
```

### Auth Test Scenarios

| Script | Description | Use Case |
|--------|-------------|----------|
| `api-authenticated.js` | Full authenticated API testing | Validate auth flow under load |
| `rate-limiting.js` | Rate limit behavior testing | Verify rate limits work correctly |
| `multi-tenant.js` | Tenant isolation verification | Ensure RLS security under load |

### Rate Limiting Tests

Test rate limiting behavior:

```bash
# Test with default rate (100 req/s)
./scripts/load-test.sh rate-limit

# Test with higher rate
k6 run --env RATE=200 tests/load/scripts/rate-limiting.js

# Extended duration
k6 run --env RATE=100 --env DURATION=5m tests/load/scripts/rate-limiting.js
```

The rate limiting test validates:
- 429 responses are returned when limits are exceeded
- Retry-After headers are present
- Recovery after rate limit window
- Both authenticated and unauthenticated limits

### Multi-Tenant Testing

Verify tenant isolation under load:

```bash
# Run multi-tenant test
./scripts/load-test.sh multi-tenant

# With multiple tenants (format: user:pass:tenant)
k6 run --env TEST_USERS=alice:pass:tenant1,bob:pass:tenant2 tests/load/scripts/multi-tenant.js

# More VUs for heavier testing
k6 run --env VUS=20 --env ITERATIONS=100 tests/load/scripts/multi-tenant.js
```

The multi-tenant test validates:
- Resources created have correct tenant_id
- Users only see their own tenant's data
- Cross-tenant access attempts are blocked
- RLS policies work under concurrent load

### Token Management

The test framework includes sophisticated token management:

**Token Pool:**
- Tokens are acquired during setup phase
- Distributed across VUs round-robin
- Automatic refresh when nearing expiry

**Token Helpers (`lib/auth.js`):**
```javascript
import { getToken, authHeaders, getValidToken, decodeToken, getTenantId } from '../lib/auth.js';

// Get token for specific user
const token = getToken('user@example.com', 'password');

// Get auto-refreshing token by user index
const accessToken = getValidToken(0);

// Get headers with auth
const headers = authHeaders(0);

// Decode token claims
const claims = decodeToken(accessToken);
const tenantId = getTenantId(accessToken);
```

**Token Pool (`lib/tokens.js`):**
```javascript
import { initializeTokenPool, getPooledToken } from '../lib/tokens.js';

// In setup()
const pool = initializeTokenPool();

// In default()
const token = getPooledToken(pool, __VU);
```

### Troubleshooting Authentication

**Token request fails:**
```bash
# Check Keycloak is running
curl http://localhost:8080

# Verify token endpoint
curl -X POST http://localhost:8080/realms/knowledge-mapper-dev/protocol/openid-connect/token \
  -d "grant_type=password&client_id=knowledge-mapper-app&username=alice@example.com&password=password123"
```

**401 errors during test:**
- Token may have expired (check `expires_in` in token response)
- Verify token refresh is working (check `token_refresh_count` metric)
- Check clock synchronization between systems

**High auth error rate:**
- Verify test users exist in Keycloak
- Check rate limits on token endpoint
- Review Keycloak logs: `docker compose logs keycloak`

**Cross-tenant errors:**
- Verify `tenant_id` claim exists in JWT tokens
- Check RLS policies in PostgreSQL
- Review middleware tenant extraction logic

### Custom Metrics

The auth tests export custom metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `auth_errors` | Rate | Authentication error rate |
| `auth_latency` | Trend | Latency for authenticated requests |
| `token_refresh_count` | Counter | Number of token refreshes |
| `authenticated_requests` | Counter | Total authenticated requests |
| `unauthorized_errors` | Counter | 401 response count |
| `forbidden_errors` | Counter | 403 response count |
| `rate_limit_hits` | Counter | 429 response count |
| `cross_tenant_errors` | Counter | Tenant isolation violations |
| `tenant_isolation_success` | Rate | Tenant isolation success rate |

## Related Documentation

- [k6 Documentation](https://k6.io/docs/)
- [k6 Extensions](https://k6.io/docs/extensions/)
- [Performance Testing Guide](https://k6.io/docs/testing-guides/)
- [k6 OAuth2 Example](https://k6.io/docs/examples/oauth-authentication/)

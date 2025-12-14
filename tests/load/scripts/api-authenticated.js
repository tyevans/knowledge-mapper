// Authenticated API Endpoint Load Tests
//
// Tests protected API endpoints with OAuth token authentication.
// Includes token acquisition, refresh, and multi-user scenarios.
//
// Features:
//   - Pre-acquired token pool for efficient testing
//   - Automatic token refresh handling
//   - Multi-user simulation
//   - Comprehensive auth error tracking
//
// Prerequisites:
//   - Test users created in Keycloak
//   - Backend running with auth enabled
//   - OAuth client configured for password grant
//
// Usage:
//   k6 run tests/load/scripts/api-authenticated.js
//   k6 run --env TEST_USERS=user1:pass1,user2:pass2 tests/load/scripts/api-authenticated.js
//   ./scripts/load-test.sh api-auth
//
// Environment Variables:
//   TOKEN_URL       - OAuth token endpoint
//   CLIENT_ID       - OAuth client ID
//   CLIENT_SECRET   - Optional client secret
//   TEST_USERS      - Comma-separated user:pass pairs
//   ACCESS_TOKEN    - Pre-provided token (bypasses pool)
//   AUTH_DEBUG      - Enable debug logging (true/false)

import http from 'k6/http';
import { check, sleep, group, fail } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { BASE_URL, API_PREFIX, defaultOptions } from '../lib/config.js';
import { authConfig, authHeaders, getValidToken, logAuthConfig, authHeadersWithToken } from '../lib/auth.js';
import { initializeTokenPool, getPooledToken, getPoolStats, logPoolStatus, refreshPooledToken } from '../lib/tokens.js';
import { thinkTime, generateTestId } from '../lib/helpers.js';
import { checkNoServerError } from '../lib/checks.js';

// Custom metrics for authentication testing
const authErrors = new Rate('auth_errors');
const authLatency = new Trend('auth_latency', true);
const tokenRefreshCount = new Counter('token_refresh_count');
const authenticatedRequests = new Counter('authenticated_requests');
const unauthorizedErrors = new Counter('unauthorized_errors');
const forbiddenErrors = new Counter('forbidden_errors');
const serverErrors = new Counter('server_errors');

// Test configuration
export const options = {
  scenarios: {
    authenticated_api: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 10 },   // Warm up
        { duration: '3m', target: 30 },   // Normal load
        { duration: '1m', target: 50 },   // Peak load
        { duration: '1m', target: 0 },    // Cool down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    // Overall performance
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.05'],

    // Auth-specific thresholds
    auth_errors: ['rate<0.05'],          // Less than 5% auth errors
    auth_latency: ['p(95)<400'],         // 95th percentile auth latency

    // Endpoint-specific thresholds
    'http_req_duration{name:me}': ['p(95)<300'],
    'http_req_duration{name:todos}': ['p(95)<500'],
    'http_req_duration{name:create_todo}': ['p(95)<500'],

    // Check pass rate
    checks: ['rate>0.90'],
  },
  tags: {
    test_type: 'authenticated',
  },
};

// Setup: Initialize token pool
export function setup() {
  console.log('\n=== Authenticated API Load Test ===');
  console.log(`Base URL: ${BASE_URL}${API_PREFIX}`);
  console.log('');

  // Log auth configuration
  logAuthConfig();
  console.log('');

  // Check for pre-provided token
  if (__ENV.ACCESS_TOKEN) {
    console.log('Using pre-provided ACCESS_TOKEN');
    return {
      startTime: new Date().toISOString(),
      useStaticToken: true,
      staticToken: __ENV.ACCESS_TOKEN,
      tokenPool: [],
    };
  }

  // Check we have test users configured
  if (authConfig.testUsers.length === 0) {
    fail('No test users configured. Set TEST_USERS environment variable.');
  }

  // Get tokens for all test users upfront
  const tokenPool = initializeTokenPool();

  if (tokenPool.length === 0) {
    fail('No valid tokens obtained - check TEST_USERS and Keycloak configuration');
  }

  // Log pool status
  logPoolStatus(tokenPool);
  console.log('');

  // Verify system is ready with an authenticated request
  const testToken = tokenPool[0].accessToken;
  const healthResponse = http.get(`${BASE_URL}${API_PREFIX}/health`, {
    headers: authHeadersWithToken(testToken),
  });

  if (healthResponse.status !== 200) {
    console.warn(`Health check returned ${healthResponse.status} - system may not be ready`);
  } else {
    console.log('Health check passed');
  }

  return {
    startTime: new Date().toISOString(),
    useStaticToken: false,
    staticToken: null,
    tokenPool: tokenPool,
  };
}

// Main test function
export default function(data) {
  let token;
  let headers;
  let userInfo = null;

  // Get token for this VU
  if (data.useStaticToken) {
    token = data.staticToken;
    headers = authHeadersWithToken(token);
  } else {
    try {
      // Try to get pooled token first (more efficient)
      const pooledToken = getPooledToken(data.tokenPool, __VU);

      // Check if token needs refresh (long-running tests)
      const remainingSeconds = (pooledToken.expiresAt - Date.now()) / 1000;
      if (remainingSeconds < authConfig.refreshThreshold) {
        tokenRefreshCount.add(1);
        refreshPooledToken(data.tokenPool, ((__VU - 1) % data.tokenPool.length));
      }

      token = pooledToken.accessToken;
      userInfo = {
        username: pooledToken.username,
        tenantId: pooledToken.tenantId,
      };
    } catch (e) {
      // Fallback to dynamic token acquisition
      console.warn(`VU ${__VU}: Falling back to dynamic token`);
      token = getValidToken(__VU % authConfig.testUsers.length);
    }

    if (!token) {
      authErrors.add(1);
      console.error(`VU ${__VU}: Failed to obtain token`);
      sleep(5);  // Back off on auth failure
      return;
    }

    headers = authHeadersWithToken(token);
  }

  // Test 1: Get current user (/me or /auth/me endpoint)
  group('user_profile', function() {
    const startTime = Date.now();

    // Try common user profile endpoints
    let response = http.get(`${BASE_URL}${API_PREFIX}/auth/me`, {
      headers: headers,
      tags: { name: 'me', authenticated: 'true', endpoint: 'auth/me' },
    });

    // Fallback to /users/me if /auth/me returns 404
    if (response.status === 404) {
      response = http.get(`${BASE_URL}${API_PREFIX}/users/me`, {
        headers: headers,
        tags: { name: 'me', authenticated: 'true', endpoint: 'users/me' },
      });
    }

    authLatency.add(Date.now() - startTime);
    authenticatedRequests.add(1);

    // Track specific error types
    if (response.status === 401) {
      unauthorizedErrors.add(1);
      authErrors.add(1);
      console.warn(`VU ${__VU}: Unauthorized (401) - token may be invalid`);
    } else if (response.status === 403) {
      forbiddenErrors.add(1);
      authErrors.add(1);
    } else if (response.status >= 500) {
      serverErrors.add(1);
      authErrors.add(1);
    } else {
      authErrors.add(0);
    }

    const success = check(response, {
      'me: status 200': (r) => r.status === 200,
      'me: has user data': (r) => {
        if (r.status !== 200) return false;
        try {
          const body = JSON.parse(r.body);
          return 'sub' in body || 'email' in body || 'user_id' in body || 'id' in body;
        } catch {
          return false;
        }
      },
      'me: response time < 300ms': (r) => r.timings.duration < 300,
    });

    if (!success && response.status !== 200) {
      // Log details for debugging
      if (__ENV.AUTH_DEBUG === 'true') {
        console.log(`VU ${__VU} /me response: ${response.status} - ${response.body.substring(0, 200)}`);
      }
    }
  });

  thinkTime(1, 2);

  // Test 2: List todos (protected, tenant-scoped endpoint)
  group('list_todos', function() {
    const startTime = Date.now();

    const response = http.get(`${BASE_URL}${API_PREFIX}/todos`, {
      headers: headers,
      tags: { name: 'todos', authenticated: 'true', endpoint: 'todos' },
    });

    authLatency.add(Date.now() - startTime);
    authenticatedRequests.add(1);

    // Track errors
    authErrors.add(response.status === 401 || response.status === 403);
    if (response.status === 401) unauthorizedErrors.add(1);
    if (response.status === 403) forbiddenErrors.add(1);
    if (response.status >= 500) serverErrors.add(1);

    check(response, {
      'todos: status 200 or 404': (r) => r.status === 200 || r.status === 404,
      'todos: returns array or paginated': (r) => {
        if (r.status !== 200) return true;  // Skip check if not 200
        try {
          const body = JSON.parse(r.body);
          return Array.isArray(body) ||
                 ('items' in body && Array.isArray(body.items)) ||
                 ('data' in body && Array.isArray(body.data));
        } catch {
          return false;
        }
      },
      'todos: response time < 500ms': (r) => r.timings.duration < 500,
    });
  });

  thinkTime(2, 4);

  // Test 3: Create and delete todo (write operations)
  group('crud_todo', function() {
    // Create a new todo
    const testId = generateTestId();
    const createPayload = JSON.stringify({
      title: `Load test todo ${testId}`,
      description: `Created by VU ${__VU} at iteration ${__ITER}`,
      completed: false,
    });

    const createResponse = http.post(`${BASE_URL}${API_PREFIX}/todos`, createPayload, {
      headers: headers,
      tags: { name: 'create_todo', authenticated: 'true', endpoint: 'todos' },
    });

    authenticatedRequests.add(1);

    // Track errors
    if (createResponse.status === 401) unauthorizedErrors.add(1);
    if (createResponse.status === 403) forbiddenErrors.add(1);
    if (createResponse.status >= 500) serverErrors.add(1);

    const created = check(createResponse, {
      'create: status 201 or 200': (r) => r.status === 201 || r.status === 200,
      'create: has id': (r) => {
        if (r.status !== 201 && r.status !== 200) return false;
        try {
          const body = JSON.parse(r.body);
          return 'id' in body;
        } catch {
          return false;
        }
      },
    });

    // If created successfully, verify tenant isolation and then delete
    if (created && (createResponse.status === 201 || createResponse.status === 200)) {
      try {
        const todoData = JSON.parse(createResponse.body);
        const todoId = todoData.id;

        // Verify tenant_id matches expected (if present)
        if (todoData.tenant_id && userInfo && userInfo.tenantId) {
          check(createResponse, {
            'create: correct tenant_id': () => todoData.tenant_id === userInfo.tenantId,
          });
        }

        if (todoId) {
          sleep(0.5);  // Brief pause before delete

          // Delete the todo to clean up
          const deleteResponse = http.del(`${BASE_URL}${API_PREFIX}/todos/${todoId}`, null, {
            headers: headers,
            tags: { name: 'delete_todo', authenticated: 'true', endpoint: 'todos' },
          });

          authenticatedRequests.add(1);

          check(deleteResponse, {
            'delete: status 204 or 200 or 404': (r) =>
              r.status === 204 || r.status === 200 || r.status === 404,
          });
        }
      } catch (e) {
        if (__ENV.AUTH_DEBUG === 'true') {
          console.log(`VU ${__VU}: Failed to parse create response: ${e.message}`);
        }
      }
    }
  });

  thinkTime(2, 4);

  // Test 4: Test unauthorized access (optional - verifies auth is working)
  if (__ITER % 10 === 0) {  // Only run every 10th iteration to reduce noise
    group('verify_auth_required', function() {
      // Try to access protected endpoint without token
      const response = http.get(`${BASE_URL}${API_PREFIX}/todos`, {
        headers: {
          'Content-Type': 'application/json',
          // No Authorization header
        },
        tags: { name: 'no_auth_test', authenticated: 'false' },
      });

      check(response, {
        'no-auth: returns 401 or 403': (r) => r.status === 401 || r.status === 403,
      });
    });
  }
}

// Teardown: Log final statistics
export function teardown(data) {
  console.log('\n=== Test Complete ===');
  console.log(`Started: ${data.startTime}`);
  console.log(`Ended: ${new Date().toISOString()}`);

  if (data.useStaticToken) {
    console.log('Used static ACCESS_TOKEN');
  } else {
    console.log(`Token pool size: ${data.tokenPool.length}`);
    if (data.tokenPool.length > 0) {
      const stats = getPoolStats(data.tokenPool);
      console.log(`Tokens valid at end: ${stats.valid}/${stats.total}`);
      console.log(`Tokens expired: ${stats.expired}`);
    }
  }
}

// Custom summary handler
export function handleSummary(data) {
  const summary = {
    timestamp: new Date().toISOString(),
    scenario: 'authenticated',
    environment: __ENV.ENVIRONMENT || 'local',
    metrics: {
      requests: {
        total: data.metrics.http_reqs?.values?.count || 0,
        authenticated: data.metrics.authenticated_requests?.values?.count || 0,
      },
      errors: {
        authErrorRate: ((data.metrics.auth_errors?.values?.rate || 0) * 100).toFixed(2) + '%',
        unauthorized: data.metrics.unauthorized_errors?.values?.count || 0,
        forbidden: data.metrics.forbidden_errors?.values?.count || 0,
        server: data.metrics.server_errors?.values?.count || 0,
      },
      duration: {
        avg: Math.round(data.metrics.http_req_duration?.values?.avg || 0),
        p95: Math.round(data.metrics.http_req_duration?.values?.['p(95)'] || 0),
        p99: Math.round(data.metrics.http_req_duration?.values?.['p(99)'] || 0),
      },
      authLatency: {
        avg: Math.round(data.metrics.auth_latency?.values?.avg || 0),
        p95: Math.round(data.metrics.auth_latency?.values?.['p(95)'] || 0),
      },
      tokenRefreshes: data.metrics.token_refresh_count?.values?.count || 0,
    },
    thresholds: {
      passed: Object.values(data.metrics).every(m => !m.thresholds || Object.values(m.thresholds).every(t => t.ok)),
    },
  };

  // Console output
  console.log('\n=== Summary ===');
  console.log(`Auth Error Rate: ${summary.metrics.errors.authErrorRate}`);
  console.log(`Avg Latency: ${summary.metrics.duration.avg}ms`);
  console.log(`P95 Latency: ${summary.metrics.duration.p95}ms`);
  console.log(`Token Refreshes: ${summary.metrics.tokenRefreshes}`);

  return {
    'results/auth-test-summary.json': JSON.stringify(summary, null, 2),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}

// Text summary helper (k6 built-in)
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

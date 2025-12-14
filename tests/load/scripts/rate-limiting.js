// Rate Limiting Behavior Load Test
//
// Tests that rate limiting is enforced correctly and returns proper responses.
// Sends high-volume requests to trigger rate limits and validates behavior.
//
// Features:
//   - High request rate to trigger limits
//   - Validates 429 response handling
//   - Checks Retry-After header compliance
//   - Tests both authenticated and unauthenticated rate limits
//
// Prerequisites:
//   - Backend running with rate limiting enabled
//   - Redis configured for rate limiting storage
//
// Usage:
//   k6 run tests/load/scripts/rate-limiting.js
//   k6 run --env RATE=200 tests/load/scripts/rate-limiting.js
//   ./scripts/load-test.sh rate-limit
//
// Environment Variables:
//   BASE_URL      - API base URL
//   RATE          - Requests per second (default: 100)
//   DURATION      - Test duration (default: 1m)
//   TEST_USERS    - For authenticated rate limit testing

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Counter, Trend } from 'k6/metrics';
import { BASE_URL, API_PREFIX, defaultOptions } from '../lib/config.js';
import { authHeaders, authConfig, getValidToken } from '../lib/auth.js';
import { initializeTokenPool, getPooledToken } from '../lib/tokens.js';

// Custom metrics for rate limiting analysis
const rateLimitHits = new Counter('rate_limit_hits');
const rateLimitRate = new Rate('rate_limit_rate');
const retryAfterValues = new Trend('retry_after_values', true);
const requestsBeforeLimit = new Counter('requests_before_limit');
const limitRecoveryTime = new Trend('limit_recovery_time', true);

// Test configuration
const targetRate = parseInt(__ENV.RATE || '100');
const testDuration = __ENV.DURATION || '1m';

export const options = {
  scenarios: {
    // Unauthenticated rate limit test
    unauthenticated_flood: {
      executor: 'constant-arrival-rate',
      rate: targetRate,
      timeUnit: '1s',
      duration: testDuration,
      preAllocatedVUs: Math.min(targetRate, 100),
      maxVUs: Math.min(targetRate * 2, 200),
      exec: 'testUnauthenticatedRateLimit',
      tags: { auth: 'false' },
    },
    // Authenticated rate limit test (runs after unauthenticated)
    authenticated_flood: {
      executor: 'constant-arrival-rate',
      rate: Math.floor(targetRate / 2),  // Lower rate for auth requests
      timeUnit: '1s',
      duration: testDuration,
      preAllocatedVUs: Math.min(targetRate / 2, 50),
      maxVUs: Math.min(targetRate, 100),
      exec: 'testAuthenticatedRateLimit',
      startTime: testDuration,  // Start after unauthenticated test
      tags: { auth: 'true' },
    },
  },
  thresholds: {
    // We expect rate limiting to kick in, so allow some "failures"
    http_req_failed: ['rate<0.50'],  // Up to 50% may be rate limited

    // Track rate limiting metrics
    rate_limit_rate: ['rate>0.01'],  // Expect at least 1% rate limited (proves limits work)

    // Response time for non-rate-limited requests
    'http_req_duration{status:200}': ['p(95)<500'],

    // 429 responses should be fast
    'http_req_duration{status:429}': ['p(95)<100'],
  },
  tags: {
    test_type: 'rate_limiting',
  },
};

// Shared data for authenticated tests
let tokenPool = null;

export function setup() {
  console.log('\n=== Rate Limiting Load Test ===');
  console.log(`Base URL: ${BASE_URL}${API_PREFIX}`);
  console.log(`Target Rate: ${targetRate} req/s`);
  console.log(`Duration: ${testDuration}`);
  console.log('');

  // Initialize tokens for authenticated tests
  if (authConfig.testUsers.length > 0) {
    console.log('Initializing token pool for authenticated tests...');
    tokenPool = initializeTokenPool();
    console.log(`Token pool: ${tokenPool.length} tokens`);
  } else {
    console.log('No test users configured - skipping authenticated rate limit tests');
    tokenPool = [];
  }

  // Verify system is ready
  const healthResponse = http.get(`${BASE_URL}${API_PREFIX}/health`);
  if (healthResponse.status !== 200) {
    console.warn(`Health check returned ${healthResponse.status}`);
  } else {
    console.log('Health check passed');
  }

  return {
    startTime: new Date().toISOString(),
    tokenPool: tokenPool,
    firstRateLimitHit: null,
    requestsUntilLimit: 0,
  };
}

// Test unauthenticated rate limiting
export function testUnauthenticatedRateLimit(data) {
  const response = http.get(`${BASE_URL}${API_PREFIX}/health`, {
    headers: defaultOptions.headers,
    tags: { name: 'rate_limit_unauth', endpoint: 'health' },
  });

  handleRateLimitResponse(response, 'unauthenticated');
}

// Test authenticated rate limiting
export function testAuthenticatedRateLimit(data) {
  // Skip if no tokens available
  if (!data.tokenPool || data.tokenPool.length === 0) {
    return;
  }

  let token;
  try {
    const pooledToken = getPooledToken(data.tokenPool, __VU);
    token = pooledToken.accessToken;
  } catch (e) {
    token = getValidToken(__VU % authConfig.testUsers.length);
  }

  if (!token) {
    return;
  }

  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };

  // Test authenticated endpoint
  const response = http.get(`${BASE_URL}${API_PREFIX}/auth/me`, {
    headers: headers,
    tags: { name: 'rate_limit_auth', endpoint: 'me' },
  });

  // Fallback endpoint if /auth/me doesn't exist
  if (response.status === 404) {
    const fallbackResponse = http.get(`${BASE_URL}${API_PREFIX}/users/me`, {
      headers: headers,
      tags: { name: 'rate_limit_auth', endpoint: 'users/me' },
    });
    handleRateLimitResponse(fallbackResponse, 'authenticated');
  } else {
    handleRateLimitResponse(response, 'authenticated');
  }
}

// Handle rate limit response and update metrics
function handleRateLimitResponse(response, testType) {
  if (response.status === 429) {
    // Rate limited
    rateLimitHits.add(1);
    rateLimitRate.add(1);

    // Check for Retry-After header
    const retryAfter = response.headers['Retry-After'] ||
                       response.headers['retry-after'] ||
                       response.headers['X-RateLimit-Reset'] ||
                       response.headers['x-ratelimit-reset'];

    if (retryAfter) {
      const retrySeconds = parseInt(retryAfter) || 1;
      retryAfterValues.add(retrySeconds);
    }

    // Validate rate limit response
    const passed = check(response, {
      'rate-limit: status 429': (r) => r.status === 429,
      'rate-limit: has retry info': (r) => {
        // Check for any rate limit headers
        const headers = Object.keys(r.headers).map(h => h.toLowerCase());
        return headers.some(h =>
          h.includes('retry') ||
          h.includes('ratelimit') ||
          h.includes('rate-limit')
        );
      },
      'rate-limit: response is fast': (r) => r.timings.duration < 100,
    });

    // Log rate limit details periodically
    if (__ITER % 100 === 0 && __ENV.AUTH_DEBUG === 'true') {
      console.log(`[${testType}] Rate limited: Retry-After=${retryAfter || 'not set'}`);
    }

  } else {
    // Not rate limited
    rateLimitRate.add(0);
    requestsBeforeLimit.add(1);

    check(response, {
      'request: not server error': (r) => r.status < 500,
      'request: successful or auth error': (r) =>
        r.status === 200 || r.status === 401 || r.status === 403,
    });
  }
}

// Alternative test: Burst rate limit test
// Tests behavior when sending a burst of requests
export function burstRateLimitTest(data) {
  group('burst_test', function() {
    const startTime = Date.now();
    let hitRateLimit = false;
    let requestCount = 0;

    // Send burst of requests until rate limited
    while (!hitRateLimit && requestCount < 100) {
      const response = http.get(`${BASE_URL}${API_PREFIX}/health`, {
        headers: defaultOptions.headers,
        tags: { name: 'burst_test' },
      });

      requestCount++;

      if (response.status === 429) {
        hitRateLimit = true;
        limitRecoveryTime.add(Date.now() - startTime);

        console.log(`Burst test: Hit rate limit after ${requestCount} requests`);

        // Wait for rate limit to reset
        const retryAfter = parseInt(response.headers['Retry-After'] || '1');
        sleep(retryAfter);

        // Verify we can make requests again
        const recoveryResponse = http.get(`${BASE_URL}${API_PREFIX}/health`);
        check(recoveryResponse, {
          'recovery: can make requests after wait': (r) => r.status === 200,
        });
      }
    }

    if (!hitRateLimit) {
      console.log(`Burst test: No rate limit hit after ${requestCount} requests`);
    }
  });
}

export function teardown(data) {
  console.log('\n=== Rate Limiting Test Complete ===');
  console.log(`Started: ${data.startTime}`);
  console.log(`Ended: ${new Date().toISOString()}`);
}

export function handleSummary(data) {
  const totalRequests = data.metrics.http_reqs?.values?.count || 0;
  const rateLimited = data.metrics.rate_limit_hits?.values?.count || 0;
  const rateLimitPercent = totalRequests > 0 ? ((rateLimited / totalRequests) * 100).toFixed(2) : 0;

  const avgRetryAfter = data.metrics.retry_after_values?.values?.avg || 0;

  console.log('\n=== Rate Limiting Summary ===');
  console.log(`Total Requests: ${totalRequests}`);
  console.log(`Rate Limited (429): ${rateLimited}`);
  console.log(`Rate Limit %: ${rateLimitPercent}%`);
  console.log(`Avg Retry-After: ${avgRetryAfter.toFixed(2)}s`);

  // Analyze if rate limiting is working as expected
  if (rateLimited === 0) {
    console.log('\nWARNING: No requests were rate limited.');
    console.log('This may indicate:');
    console.log('  - Rate limiting is not enabled');
    console.log('  - Rate limits are set too high');
    console.log('  - Test rate was too low to trigger limits');
  } else if (rateLimitPercent > 80) {
    console.log('\nWARNING: Very high rate limit percentage.');
    console.log('This may indicate:');
    console.log('  - Rate limits are set too low');
    console.log('  - System is under heavy load');
  } else {
    console.log('\nRate limiting appears to be working correctly.');
  }

  const summary = {
    timestamp: new Date().toISOString(),
    scenario: 'rate_limiting',
    metrics: {
      totalRequests: totalRequests,
      rateLimited: rateLimited,
      rateLimitPercent: parseFloat(rateLimitPercent),
      avgRetryAfter: avgRetryAfter,
      duration: {
        avg: data.metrics.http_req_duration?.values?.avg || 0,
        p95: data.metrics.http_req_duration?.values?.['p(95)'] || 0,
      },
    },
    rateLimitingWorking: rateLimited > 0 && rateLimitPercent < 80,
  };

  return {
    'results/rate-limit-summary.json': JSON.stringify(summary, null, 2),
  };
}

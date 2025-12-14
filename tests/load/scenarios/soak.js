// Soak Test Scenario
//
// Extended duration test to identify memory leaks, resource exhaustion,
// and other issues that only appear over time.
//
// Usage:
//   k6 run tests/load/scenarios/soak.js
//   k6 run --env VUS=30 --env DURATION=1h tests/load/scenarios/soak.js
//   ./scripts/load-test.sh soak

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { BASE_URL, API_PREFIX, defaultOptions } from '../lib/config.js';
import { scenarios } from '../k6.config.js';
import { thinkTime } from '../lib/helpers.js';

// Custom metrics for long-running analysis
const errorRate = new Rate('error_rate');
const requestDuration = new Trend('request_duration', true);
const errorCount = new Counter('error_count');
const requestCount = new Counter('request_count');
const iterationDuration = new Trend('iteration_duration', true);

// Allow overrides via environment
const targetVUs = __ENV.VUS ? parseInt(__ENV.VUS) : 20;
const testDuration = __ENV.DURATION || '30m';

export const options = {
  scenarios: {
    soak_test: {
      executor: 'constant-vus',
      vus: targetVUs,
      duration: testDuration,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    error_rate: ['rate<0.01'],
    checks: ['rate>0.95'],
  },
  tags: {
    test_type: 'soak',
    scenario: 'soak',
    target_vus: String(targetVUs),
  },
};

export function setup() {
  console.log(`\n=== Soak Test Configuration ===`);
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`VUs: ${targetVUs} (constant)`);
  console.log(`Duration: ${testDuration}`);
  console.log(`Purpose: Detect memory leaks and resource exhaustion\n`);

  // Verify system is ready
  const healthCheck = http.get(`${BASE_URL}${API_PREFIX}/health`);
  if (healthCheck.status !== 200) {
    throw new Error(`System not ready: health check returned ${healthCheck.status}`);
  }

  return {
    startTime: new Date().toISOString(),
    targetVUs: targetVUs,
    duration: testDuration,
  };
}

export default function() {
  const iterationStart = new Date().getTime();

  // Health check
  group('health', function() {
    const response = http.get(`${BASE_URL}${API_PREFIX}/health`, {
      tags: { name: 'health' },
    });

    requestDuration.add(response.timings.duration);
    requestCount.add(1);
    errorRate.add(response.status !== 200);

    if (response.status !== 200) {
      errorCount.add(1);
    }

    check(response, {
      'health: status 200': (r) => r.status === 200,
      'health: response < 200ms': (r) => r.timings.duration < 200,
    });
  });

  thinkTime(2, 4);

  // API endpoint
  group('api', function() {
    const response = http.get(`${BASE_URL}/openapi.json`, {
      ...defaultOptions,
      tags: { name: 'openapi' },
    });

    requestDuration.add(response.timings.duration);
    requestCount.add(1);
    errorRate.add(response.status !== 200);

    if (response.status !== 200) {
      errorCount.add(1);
    }

    check(response, {
      'openapi: status 200': (r) => r.status === 200,
      'openapi: response < 500ms': (r) => r.timings.duration < 500,
    });
  });

  thinkTime(3, 6);

  // Track iteration duration
  const iterationEnd = new Date().getTime();
  iterationDuration.add(iterationEnd - iterationStart);

  // Periodic status log (every 100 iterations per VU)
  if (__ITER % 100 === 0) {
    console.log(`VU ${__VU}: Completed ${__ITER} iterations`);
  }
}

export function teardown(data) {
  const endTime = new Date().toISOString();
  const startDate = new Date(data.startTime);
  const endDate = new Date(endTime);
  const durationMs = endDate - startDate;
  const durationMin = (durationMs / 60000).toFixed(2);

  console.log(`\n=== Soak Test Complete ===`);
  console.log(`Started: ${data.startTime}`);
  console.log(`Ended: ${endTime}`);
  console.log(`Actual Duration: ${durationMin} minutes`);
}

export function handleSummary(data) {
  const summary = {
    timestamp: new Date().toISOString(),
    scenario: 'soak',
    configuration: {
      vus: targetVUs,
      duration: testDuration,
    },
    metrics: {
      totalRequests: data.metrics.request_count?.values?.count || 0,
      totalErrors: data.metrics.error_count?.values?.count || 0,
      errorRate: (data.metrics.http_req_failed?.values?.rate || 0) * 100,
      duration: {
        avg: data.metrics.http_req_duration?.values?.avg || 0,
        med: data.metrics.http_req_duration?.values?.med || 0,
        p90: data.metrics.http_req_duration?.values?.['p(90)'] || 0,
        p95: data.metrics.http_req_duration?.values?.['p(95)'] || 0,
        p99: data.metrics.http_req_duration?.values?.['p(99)'] || 0,
        max: data.metrics.http_req_duration?.values?.max || 0,
      },
      throughput: {
        requestsPerSecond: data.metrics.http_reqs?.values?.rate || 0,
      },
    },
    passed: data.metrics.checks?.values?.rate >= 0.95,
  };

  console.log('\n=== Soak Test Summary ===');
  console.log(`Total Requests: ${summary.metrics.totalRequests}`);
  console.log(`Total Errors: ${summary.metrics.totalErrors}`);
  console.log(`Error Rate: ${summary.metrics.errorRate.toFixed(2)}%`);
  console.log(`Avg Duration: ${summary.metrics.duration.avg.toFixed(2)}ms`);
  console.log(`P95 Duration: ${summary.metrics.duration.p95.toFixed(2)}ms`);
  console.log(`P99 Duration: ${summary.metrics.duration.p99.toFixed(2)}ms`);
  console.log(`Max Duration: ${summary.metrics.duration.max.toFixed(2)}ms`);
  console.log(`Throughput: ${summary.metrics.throughput.requestsPerSecond.toFixed(2)} req/s`);
  console.log(`\nStatus: ${summary.passed ? 'PASSED' : 'FAILED'}`);

  return {
    'results/soak-test-summary.json': JSON.stringify(summary, null, 2),
  };
}

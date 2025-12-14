// Load Test Scenario
//
// Normal expected load test to validate performance under typical conditions.
// Ramps up to target VUs, holds steady, then ramps down.
//
// Usage:
//   k6 run tests/load/scenarios/load.js
//   k6 run --env VUS=100 --env DURATION=10m tests/load/scenarios/load.js
//   ./scripts/load-test.sh load

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { BASE_URL, API_PREFIX, defaultOptions } from '../lib/config.js';
import { scenarios } from '../k6.config.js';
import { thinkTime } from '../lib/helpers.js';

// Custom metrics for detailed analysis
const errorRate = new Rate('error_rate');
const healthDuration = new Trend('health_duration', true);
const apiDuration = new Trend('api_duration', true);

// Allow VU count override via environment
const targetVUs = __ENV.VUS ? parseInt(__ENV.VUS) : 50;

export const options = {
  scenarios: {
    load_test: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: targetVUs },     // Ramp up
        { duration: __ENV.DURATION || '5m', target: targetVUs },  // Steady state
        { duration: '2m', target: 0 },             // Ramp down
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    error_rate: ['rate<0.01'],
    health_duration: ['p(95)<100'],
    api_duration: ['p(95)<500'],
    checks: ['rate>0.95'],
  },
  tags: {
    test_type: 'load',
    scenario: 'load',
    target_vus: String(targetVUs),
  },
};

export function setup() {
  console.log(`\n=== Load Test Configuration ===`);
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Target VUs: ${targetVUs}`);
  console.log(`Duration: ${__ENV.DURATION || '5m'} (steady state)`);

  // Verify system is ready
  const healthCheck = http.get(`${BASE_URL}${API_PREFIX}/health`);
  if (healthCheck.status !== 200) {
    throw new Error(`System not ready: health check returned ${healthCheck.status}`);
  }

  return {
    startTime: new Date().toISOString(),
    targetVUs: targetVUs,
  };
}

export default function() {
  // Health check (lightweight, frequent)
  group('health', function() {
    const response = http.get(`${BASE_URL}${API_PREFIX}/health`, {
      tags: { name: 'health' },
    });

    healthDuration.add(response.timings.duration);
    errorRate.add(response.status !== 200);

    check(response, {
      'health: status 200': (r) => r.status === 200,
    });
  });

  thinkTime(1, 2);

  // API endpoint (heavier, less frequent)
  group('api', function() {
    const response = http.get(`${BASE_URL}/openapi.json`, {
      ...defaultOptions,
      tags: { name: 'openapi' },
    });

    apiDuration.add(response.timings.duration);
    errorRate.add(response.status !== 200);

    check(response, {
      'openapi: status 200': (r) => r.status === 200,
    });
  });

  thinkTime(2, 4);
}

export function teardown(data) {
  console.log(`\n=== Load Test Complete ===`);
  console.log(`Started: ${data.startTime}`);
  console.log(`Ended: ${new Date().toISOString()}`);
}

export function handleSummary(data) {
  const summary = {
    timestamp: new Date().toISOString(),
    scenario: 'load',
    targetVUs: data.options?.scenarios?.load_test?.stages?.[1]?.target || 'unknown',
    metrics: {
      requests: data.metrics.http_reqs?.values?.count || 0,
      errorRate: (data.metrics.http_req_failed?.values?.rate || 0) * 100,
      duration: {
        avg: data.metrics.http_req_duration?.values?.avg || 0,
        p95: data.metrics.http_req_duration?.values?.['p(95)'] || 0,
        p99: data.metrics.http_req_duration?.values?.['p(99)'] || 0,
      },
    },
    passed: data.metrics.checks?.values?.rate >= 0.95,
  };

  return {
    'results/load-test-summary.json': JSON.stringify(summary, null, 2),
  };
}

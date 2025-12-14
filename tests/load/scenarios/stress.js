// Stress Test Scenario
//
// Tests system behavior beyond normal load to find breaking points.
// Progressively increases load to identify capacity limits.
//
// Usage:
//   k6 run tests/load/scenarios/stress.js
//   ./scripts/load-test.sh stress

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { BASE_URL, API_PREFIX, defaultOptions } from '../lib/config.js';
import { thinkTime } from '../lib/helpers.js';

// Custom metrics
const errorRate = new Rate('error_rate');
const requestDuration = new Trend('request_duration', true);
const errorCount = new Counter('error_count');

export const options = {
  scenarios: {
    stress_test: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },   // Ramp to normal load
        { duration: '3m', target: 50 },   // Hold normal
        { duration: '2m', target: 100 },  // Ramp to high load
        { duration: '3m', target: 100 },  // Hold high
        { duration: '2m', target: 150 },  // Ramp to stress
        { duration: '3m', target: 150 },  // Hold stress
        { duration: '2m', target: 200 },  // Ramp to breaking point
        { duration: '3m', target: 200 },  // Hold breaking point
        { duration: '5m', target: 0 },    // Recovery
      ],
    },
  },
  thresholds: {
    // More lenient thresholds for stress testing
    http_req_duration: ['p(95)<2000'],  // Allow up to 2s under stress
    http_req_failed: ['rate<0.10'],     // Allow up to 10% errors under stress
    checks: ['rate>0.80'],              // 80% checks must pass
  },
  tags: {
    test_type: 'stress',
    scenario: 'stress',
  },
};

export function setup() {
  console.log(`\n=== Stress Test Configuration ===`);
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Peak VUs: 200`);
  console.log(`Total Duration: ~25 minutes`);
  console.log(`Purpose: Find breaking points and observe recovery\n`);

  return { startTime: new Date().toISOString() };
}

export default function() {
  const response = http.get(`${BASE_URL}${API_PREFIX}/health`, {
    tags: { name: 'health' },
    timeout: '10s',  // Longer timeout for stress conditions
  });

  requestDuration.add(response.timings.duration);
  errorRate.add(response.status !== 200);

  if (response.status !== 200) {
    errorCount.add(1);
    console.log(`Error: ${response.status} at VU ${__VU}, iteration ${__ITER}`);
  }

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 2s': (r) => r.timings.duration < 2000,
  });

  // Minimal think time during stress testing
  sleep(0.5);
}

export function teardown(data) {
  console.log(`\n=== Stress Test Complete ===`);
  console.log(`Started: ${data.startTime}`);
  console.log(`Ended: ${new Date().toISOString()}`);
}

export function handleSummary(data) {
  const summary = {
    timestamp: new Date().toISOString(),
    scenario: 'stress',
    peakVUs: 200,
    metrics: {
      requests: data.metrics.http_reqs?.values?.count || 0,
      errors: data.metrics.error_count?.values?.count || 0,
      errorRate: (data.metrics.http_req_failed?.values?.rate || 0) * 100,
      duration: {
        avg: data.metrics.http_req_duration?.values?.avg || 0,
        p95: data.metrics.http_req_duration?.values?.['p(95)'] || 0,
        p99: data.metrics.http_req_duration?.values?.['p(99)'] || 0,
        max: data.metrics.http_req_duration?.values?.max || 0,
      },
    },
  };

  return {
    'results/stress-test-summary.json': JSON.stringify(summary, null, 2),
  };
}

// Smoke Test Scenario
//
// Quick validation test to ensure the application is working.
// Run before more intensive tests to catch obvious issues.
//
// Usage:
//   k6 run tests/load/scenarios/smoke.js
//   ./scripts/load-test.sh smoke

import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, API_PREFIX } from '../lib/config.js';
import { scenarios } from '../k6.config.js';

export const options = {
  ...scenarios.smoke,
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],  // 99% of checks must pass
  },
  tags: {
    test_type: 'smoke',
    scenario: 'smoke',
  },
};

export default function() {
  // Test 1: Health check
  const healthRes = http.get(`${BASE_URL}${API_PREFIX}/health`);
  check(healthRes, {
    'health endpoint accessible': (r) => r.status === 200,
    'health returns healthy status': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.status === 'healthy' || body.status === 'ok';
      } catch {
        return false;
      }
    },
  });

  sleep(1);

  // Test 2: OpenAPI spec accessible
  const openApiRes = http.get(`${BASE_URL}/openapi.json`);
  check(openApiRes, {
    'openapi accessible': (r) => r.status === 200,
    'openapi valid JSON': (r) => {
      try {
        JSON.parse(r.body);
        return true;
      } catch {
        return false;
      }
    },
  });

  sleep(1);
}

export function handleSummary(data) {
  const passed = data.metrics.checks.values.rate >= 0.99;

  console.log('\n=== Smoke Test Summary ===');
  console.log(`Total Requests: ${data.metrics.http_reqs.values.count}`);
  console.log(`Failed Requests: ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%`);
  console.log(`Avg Duration: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms`);
  console.log(`P95 Duration: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms`);
  console.log(`\nStatus: ${passed ? 'PASSED' : 'FAILED'}`);

  const summary = {
    timestamp: new Date().toISOString(),
    scenario: 'smoke',
    passed: passed,
    metrics: {
      requests: data.metrics.http_reqs.values.count,
      errorRate: data.metrics.http_req_failed.values.rate * 100,
      duration: {
        avg: data.metrics.http_req_duration.values.avg,
        p95: data.metrics.http_req_duration.values['p(95)'],
      },
      checksPassRate: data.metrics.checks.values.rate * 100,
    },
  };

  return {
    'results/smoke-test-summary.json': JSON.stringify(summary, null, 2),
  };
}

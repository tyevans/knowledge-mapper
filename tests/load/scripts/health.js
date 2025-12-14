// Health Endpoint Load Tests
//
// Tests the /health endpoint to establish baseline performance.
// This is typically the fastest endpoint and serves as a sanity check.
//
// Usage:
//   k6 run tests/load/scripts/health.js
//   k6 run --env BASE_URL=https://api.example.com tests/load/scripts/health.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { BASE_URL, API_PREFIX } from '../lib/config.js';
import { checkHealthResponse } from '../lib/checks.js';

// Custom metrics
const healthCheckErrors = new Rate('health_check_errors');
const healthCheckDuration = new Trend('health_check_duration');

// Test configuration
export const options = {
  scenarios: {
    health_check: {
      executor: 'constant-vus',
      vus: __ENV.VUS ? parseInt(__ENV.VUS) : 10,
      duration: __ENV.DURATION || '1m',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<100', 'p(99)<200'],
    http_req_failed: ['rate<0.001'],
    health_check_errors: ['rate<0.001'],
    health_check_duration: ['p(95)<100'],
  },
  tags: {
    test_type: 'health',
  },
};

// Test setup (runs once per VU)
export function setup() {
  console.log(`Testing health endpoint at: ${BASE_URL}${API_PREFIX}/health`);

  // Verify endpoint is accessible
  const response = http.get(`${BASE_URL}${API_PREFIX}/health`);
  if (response.status !== 200) {
    throw new Error(`Health endpoint not accessible: ${response.status}`);
  }

  return { startTime: new Date().toISOString() };
}

// Main test function (runs repeatedly)
export default function() {
  const response = http.get(`${BASE_URL}${API_PREFIX}/health`, {
    tags: { name: 'health' },
  });

  // Record custom metrics
  healthCheckDuration.add(response.timings.duration);
  healthCheckErrors.add(response.status !== 200);

  // Run checks
  checkHealthResponse(response);

  // Small pause between requests
  sleep(0.1);
}

// Teardown (runs once at end)
export function teardown(data) {
  console.log(`Test completed. Started at: ${data.startTime}`);
}

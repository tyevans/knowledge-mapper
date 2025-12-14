// Public API Endpoint Load Tests
//
// Tests unauthenticated API endpoints.
// Focuses on publicly accessible endpoints like health, OpenAPI schema.
//
// Usage:
//   k6 run tests/load/scripts/api-public.js

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { BASE_URL, API_PREFIX, defaultOptions } from '../lib/config.js';
import { checkOk, checkJsonBody, checkDuration } from '../lib/checks.js';
import { thinkTime } from '../lib/helpers.js';

// Custom metrics
const apiErrors = new Rate('api_errors');
const requestCount = new Counter('request_count');

// Test configuration
export const options = {
  scenarios: {
    public_api: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 10 },  // Warm up
        { duration: '2m', target: 30 },   // Normal load
        { duration: '30s', target: 0 },   // Cool down
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    api_errors: ['rate<0.01'],
  },
  tags: {
    test_type: 'api_public',
  },
};

export function setup() {
  console.log(`Testing public API at: ${BASE_URL}${API_PREFIX}`);
  return { baseUrl: BASE_URL, apiPrefix: API_PREFIX };
}

export default function(data) {
  // Test health endpoint
  group('health', function() {
    const response = http.get(`${BASE_URL}${API_PREFIX}/health`, {
      ...defaultOptions,
      tags: { name: 'health', endpoint: 'health' },
    });

    requestCount.add(1);
    apiErrors.add(response.status !== 200);

    check(response, {
      'health: status 200': (r) => r.status === 200,
      'health: has status field': (r) => {
        try {
          const body = JSON.parse(r.body);
          return 'status' in body;
        } catch {
          return false;
        }
      },
    });
  });

  thinkTime(0.5, 1);

  // Test OpenAPI schema endpoint
  group('openapi', function() {
    const response = http.get(`${BASE_URL}/openapi.json`, {
      ...defaultOptions,
      tags: { name: 'openapi', endpoint: 'openapi' },
    });

    requestCount.add(1);
    apiErrors.add(response.status !== 200);

    check(response, {
      'openapi: status 200': (r) => r.status === 200,
      'openapi: valid JSON': (r) => {
        try {
          JSON.parse(r.body);
          return true;
        } catch {
          return false;
        }
      },
      'openapi: has paths': (r) => {
        try {
          const body = JSON.parse(r.body);
          return 'paths' in body;
        } catch {
          return false;
        }
      },
    });
  });

  thinkTime(0.5, 1);

  // Test root endpoint (if exists)
  group('root', function() {
    const response = http.get(`${BASE_URL}/`, {
      ...defaultOptions,
      tags: { name: 'root', endpoint: 'root' },
    });

    requestCount.add(1);
    // Root may redirect or return various codes, so we're lenient
    apiErrors.add(response.status >= 500);

    check(response, {
      'root: not server error': (r) => r.status < 500,
    });
  });

  thinkTime(1, 2);
}

export function teardown(data) {
  console.log('Public API test completed');
}

// k6 Configuration for Knowledge Mapper
//
// This file defines shared configuration for all load test scenarios.
// Override via environment variables or command-line options.

export const config = {
  // Base URL for API requests
  baseUrl: __ENV.BASE_URL || 'http://localhost:8000',

  // API prefix
  apiPrefix: '/api/v1',

  // Default thresholds (can be overridden per scenario)
  thresholds: {
    // 95% of requests should complete under 500ms
    http_req_duration: ['p(95)<500'],
    // Less than 1% error rate
    http_req_failed: ['rate<0.01'],
    // Specific endpoint thresholds
    'http_req_duration{name:health}': ['p(95)<100'],
    'http_req_duration{name:api}': ['p(95)<500'],
  },

  // Tags for grouping metrics
  tags: {
    project: 'knowledge-mapper',
    environment: __ENV.ENVIRONMENT || 'local',
  },
};

// Scenario presets
export const scenarios = {
  smoke: {
    executor: 'constant-vus',
    vus: 1,
    duration: '1m',
  },
  load: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '2m', target: 50 },   // Ramp up to 50 VUs
      { duration: '5m', target: 50 },   // Stay at 50 VUs
      { duration: '2m', target: 0 },    // Ramp down to 0
    ],
  },
  stress: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '2m', target: 50 },   // Ramp up
      { duration: '5m', target: 50 },   // Normal load
      { duration: '2m', target: 100 },  // Push to stress
      { duration: '5m', target: 100 },  // Hold at stress
      { duration: '2m', target: 150 },  // Breaking point
      { duration: '5m', target: 150 },  // Hold at breaking
      { duration: '5m', target: 0 },    // Recovery
    ],
  },
  soak: {
    executor: 'constant-vus',
    vus: 20,
    duration: '30m',
  },
};

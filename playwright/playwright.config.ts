import { defineConfig } from '@playwright/test';

/**
 * Playwright configuration for API testing
 * @see https://playwright.dev/docs/api-testing
 */
export default defineConfig({
  // Test directory
  testDir: './tests',

  // Test file pattern - only API spec files
  testMatch: '**/*.api.spec.ts',

  // Timeout per test (30 seconds)
  timeout: 30000,

  // Expect timeout (10 seconds)
  expect: {
    timeout: 10000,
  },

  // Run tests in parallel
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Limit workers on CI for stability
  workers: process.env.CI ? 1 : undefined,

  // Reporter configuration
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],

  // Shared settings for all projects
  use: {
    // Base URL for API requests
    baseURL: process.env.BASE_URL || 'http://localhost:8000',

    // Collect trace on first retry
    trace: 'on-first-retry',

    // Default headers for API requests
    // Note: Content-Type is intentionally omitted to allow form data for Keycloak auth
    extraHTTPHeaders: {
      'Accept': 'application/json',
    },
  },

  // Configure projects
  projects: [
    {
      name: 'API Tests',
      testMatch: '**/*.api.spec.ts',
    },
  ],

  // Note: webServer is not configured because docker compose up -d exits immediately.
  // Run `docker compose up` or `make docker-up` before running tests.
});

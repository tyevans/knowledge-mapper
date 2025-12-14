/**
 * Basic API endpoint tests using manual authentication
 *
 * This file demonstrates the manual authentication pattern where tokens
 * are retrieved explicitly using auth-helper functions. This pattern is
 * useful for:
 * - Custom authentication scenarios
 * - Testing invalid tokens
 * - Understanding the authentication flow
 *
 * For most tests, prefer the fixture pattern in api-with-fixtures.api.spec.ts
 */

import { test, expect } from '@playwright/test';
import { getAdminToken, getTestUserToken, authHeader } from './auth-helper';

/**
 * Public API Endpoints
 * These endpoints do not require authentication
 */
test.describe('Public API Endpoints', () => {
  test('GET / should return service info', async ({ request }) => {
    const response = await request.get('/');

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('service');
    expect(data).toHaveProperty('version');
    expect(data).toHaveProperty('docs');
    expect(data).toHaveProperty('health');
  });

  test('GET /api/v1/health should return healthy status', async ({ request }) => {
    const response = await request.get('/api/v1/health');

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('status', 'healthy');
    expect(data).toHaveProperty('service');
    expect(data).toHaveProperty('version');
    expect(data).toHaveProperty('timestamp');
  });

  test('GET /api/v1/health/ready should return ready status', async ({ request }) => {
    const response = await request.get('/api/v1/ready');

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('status', 'ready');
    expect(data).toHaveProperty('service');
    expect(data).toHaveProperty('version');
  });
});

/**
 * Protected API Endpoints
 * These endpoints require a valid JWT token but no specific role
 */
test.describe('Protected API Endpoints', () => {
  test('GET /api/v1/test/protected should fail without token', async ({ request }) => {
    const response = await request.get('/api/v1/test/protected');

    // Backend returns 401 or 403 for unauthenticated requests
    expect([401, 403]).toContain(response.status());
  });

  test('GET /api/v1/test/protected should succeed with admin token', async ({ request }) => {
    const token = await getAdminToken(request);
    const response = await request.get('/api/v1/test/protected', {
      headers: authHeader(token),
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('message', 'Authentication successful');
    expect(data).toHaveProperty('user_id');
    expect(data).toHaveProperty('tenant_id');
  });

  test('GET /api/v1/test/protected should succeed with user token', async ({ request }) => {
    const token = await getTestUserToken(request);
    const response = await request.get('/api/v1/test/protected', {
      headers: authHeader(token),
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('message', 'Authentication successful');
    expect(data).toHaveProperty('user_id');
    expect(data).toHaveProperty('tenant_id');
  });
});

/**
 * Admin-Only API Endpoints
 * These endpoints require the 'admin' role
 */
test.describe('Admin-Only API Endpoints', () => {
  test('GET /api/v1/test/admin should fail without token', async ({ request }) => {
    const response = await request.get('/api/v1/test/admin');

    expect([401, 403]).toContain(response.status());
  });

  test('GET /api/v1/test/admin should succeed with admin token', async ({ request }) => {
    const token = await getAdminToken(request);
    const response = await request.get('/api/v1/test/admin', {
      headers: authHeader(token),
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('message', 'This is an admin route');
    expect(data).toHaveProperty('user');
    expect(data.user).toHaveProperty('username');
    expect(data.user).toHaveProperty('roles');
    expect(data.user.roles).toContain('admin');
  });

  test('GET /api/v1/test/admin should fail with regular user token', async ({ request }) => {
    const token = await getTestUserToken(request);
    const response = await request.get('/api/v1/test/admin', {
      headers: authHeader(token),
    });

    expect(response.status()).toBe(403);
    const data = await response.json();
    expect(data.error.message).toContain("Role 'admin' required");
  });
});

/**
 * Token Validation
 * Tests for invalid, malformed, and expired tokens
 */
test.describe('Token Validation', () => {
  test('should reject request with invalid token format', async ({ request }) => {
    const response = await request.get('/api/v1/test/protected', {
      headers: authHeader('invalid.token.here'),
    });

    expect(response.status()).toBe(401);
    const data = await response.json();
    expect(data).toHaveProperty('error');
  });

  test('should reject request with malformed JWT', async ({ request }) => {
    // This is a structurally valid JWT but with invalid signature
    const fakeToken =
      'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.' +
      'eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.' +
      'POstGetfAytaZS82wHcjoTyoqhMyxXiWdR7Nn7A28cN';

    const response = await request.get('/api/v1/test/protected', {
      headers: authHeader(fakeToken),
    });

    expect(response.status()).toBe(401);
  });

  test('should reject request with empty Authorization header', async ({ request }) => {
    const response = await request.get('/api/v1/test/protected', {
      headers: { Authorization: '' },
    });

    expect([401, 403]).toContain(response.status());
  });

  test('should reject request with invalid Authorization scheme', async ({ request }) => {
    const token = await getAdminToken(request);
    const response = await request.get('/api/v1/test/protected', {
      headers: { Authorization: `Basic ${token}` }, // Wrong scheme
    });

    expect([401, 403]).toContain(response.status());
  });
});

/**
 * HTTP Methods with Authentication
 * Verify different HTTP methods work with authentication
 */
test.describe('HTTP Methods with Authentication', () => {
  test('POST request with authentication should work', async ({ request }) => {
    const token = await getTestUserToken(request);
    // POST to a hypothetical endpoint - will likely 404 but tests auth works
    const response = await request.post('/api/v1/test/echo', {
      headers: authHeader(token),
      data: { test: 'data' },
    });

    // We expect 404 (endpoint doesn't exist) or 405 (method not allowed)
    // but NOT 401/403 (auth should pass)
    if (response.status() === 401 || response.status() === 403) {
      // If we get auth error, something is wrong
      expect(response.status()).not.toBe(401);
      expect(response.status()).not.toBe(403);
    }
  });
});

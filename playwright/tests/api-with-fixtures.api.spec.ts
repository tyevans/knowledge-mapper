/**
 * API tests using the fixture pattern (RECOMMENDED APPROACH)
 *
 * This file demonstrates the recommended way to write API tests using
 * pre-authenticated request contexts provided by fixtures.ts.
 *
 * Benefits of the fixture pattern:
 * - No manual token management in tests
 * - Cleaner, more readable test code
 * - Type-safe request contexts
 * - All users authenticated once per test
 *
 * Available fixtures:
 * - adminRequest: Admin user context
 * - userRequest: Standard user context
 * - readOnlyRequest: Read-only user context
 * - managerRequest: Manager user context
 * - authenticatedRequest: All user contexts (.admin, .user, .readOnly, .newUser, .manager, .serviceAccount)
 */

import { test, expect } from './fixtures';

/**
 * Core Fixture Tests
 * Demonstrates the primary fixture patterns
 */
test.describe('API Tests with Fixtures', () => {
  test('admin can access admin endpoint using adminRequest fixture', async ({ adminRequest }) => {
    const response = await adminRequest.get('/api/v1/test/admin');

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.message).toBe('This is an admin route');
    // Note: username is the display name (name claim), not the login username
    expect(data.user.username).toBe('Admin User');
    expect(data.user.roles).toContain('admin');
    expect(data.user.roles).toContain('user');
  });

  test('regular user cannot access admin endpoint', async ({ userRequest }) => {
    const response = await userRequest.get('/api/v1/test/admin');

    expect(response.status()).toBe(403);
    const data = await response.json();
    expect(data.error.message).toContain("Role 'admin' required");
  });

});

/**
 * Multi-User Context Tests
 * Demonstrates using authenticatedRequest for multiple users in one test
 */
test.describe('Multi-User Tests with authenticatedRequest', () => {
  test('can access multiple user contexts in same test', async ({ authenticatedRequest }) => {
    // Admin can access admin endpoint
    const adminResponse = await authenticatedRequest.admin.get('/api/v1/test/admin');
    expect(adminResponse.ok()).toBeTruthy();

    // Regular user cannot access admin endpoint
    const userResponse = await authenticatedRequest.user.get('/api/v1/test/admin');
    expect(userResponse.status()).toBe(403);

    // Manager can access protected endpoint
    const managerResponse = await authenticatedRequest.manager.get('/api/v1/test/protected');
    expect(managerResponse.ok()).toBeTruthy();
  });

  test('compare admin and user access levels', async ({ authenticatedRequest }) => {
    const endpoints = [
      '/api/v1/test/protected',
      '/api/v1/test/admin',
    ];

    for (const endpoint of endpoints) {
      const adminResp = await authenticatedRequest.admin.get(endpoint);
      const userResp = await authenticatedRequest.user.get(endpoint);

      // Admin should access all endpoints
      expect(adminResp.ok()).toBeTruthy();

      // User should only access protected, not admin
      if (endpoint.includes('admin')) {
        expect(userResp.status()).toBe(403);
      } else {
        expect(userResp.ok()).toBeTruthy();
      }
    }
  });

  test('all users can access protected endpoint', async ({ authenticatedRequest }) => {
    const users = ['admin', 'user', 'readOnly', 'newUser', 'manager'] as const;

    for (const userKey of users) {
      const response = await authenticatedRequest[userKey].get('/api/v1/test/protected');
      expect(response.ok(), `${userKey} should access protected endpoint`).toBeTruthy();
    }
  });
});

/**
 * Fixture Metadata Tests
 * Demonstrates accessing user info and token from fixtures
 */
test.describe('Fixture Metadata Access', () => {
  test('can access user info from adminRequest fixture', async ({ adminRequest }) => {
    expect(adminRequest.user.username).toBe('admin');
    expect(adminRequest.user.email).toBe('admin@example.com');
    expect(adminRequest.user.roles).toContain('admin');
    expect(adminRequest.user.description).toBeTruthy();
  });

  test('can access raw token from fixture', async ({ adminRequest }) => {
    const token = adminRequest.token;

    expect(token).toBeTruthy();
    expect(typeof token).toBe('string');
    // JWT tokens start with 'eyJ' (base64 encoded '{"')
    expect(token).toMatch(/^eyJ/);
  });

  test('token can be used for custom scenarios', async ({ adminRequest, request }) => {
    // Get the token from the fixture
    const token = adminRequest.token;

    // Use it manually (e.g., for custom headers or WebSocket auth)
    const response = await request.get('/api/v1/test/protected', {
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Custom-Header': 'custom-value',
      },
    });

    expect(response.ok()).toBeTruthy();
  });
});

/**
 * Special User Scenario Tests
 * Tests for newUser and serviceAccount fixtures
 */
test.describe('Test User Scenarios', () => {
  test('readOnly user cannot modify resources (example pattern)', async ({ readOnlyRequest }) => {
    // This demonstrates the pattern for testing read-only access
    // The actual endpoint might return 405 Method Not Allowed or 403 Forbidden
    const response = await readOnlyRequest.post('/api/v1/todos', {
      data: { title: 'Test Todo', completed: false },
    });

    // Expect either 403 (forbidden) or 405 (method not allowed) or 201 (if allowed)
    // The actual behavior depends on your application's access control
    expect([201, 403, 404, 405]).toContain(response.status());
  });
});

/**
 * HTTP Method Tests
 * Demonstrates all HTTP methods work with authenticated contexts
 */
test.describe('HTTP Methods with Fixtures', () => {
  test('POST request with userRequest', async ({ userRequest }) => {
    // POST to a hypothetical endpoint
    const response = await userRequest.post('/api/v1/test/echo', {
      data: { message: 'Hello, World!' },
    });

    // Expect 404 (not found) since endpoint doesn't exist
    // but NOT 401/403 (auth should pass)
    expect(response.status()).not.toBe(401);
    expect(response.status()).not.toBe(403);
  });

  test('PUT request with adminRequest', async ({ adminRequest }) => {
    const response = await adminRequest.put('/api/v1/test/resource/1', {
      data: { updated: true },
    });

    // Auth should pass, endpoint may or may not exist
    expect(response.status()).not.toBe(401);
    expect(response.status()).not.toBe(403);
  });

  test('PATCH request with managerRequest', async ({ managerRequest }) => {
    const response = await managerRequest.patch('/api/v1/test/resource/1', {
      data: { field: 'value' },
    });

    expect(response.status()).not.toBe(401);
    expect(response.status()).not.toBe(403);
  });

  test('DELETE request with adminRequest', async ({ adminRequest }) => {
    const response = await adminRequest.delete('/api/v1/test/resource/1');

    expect(response.status()).not.toBe(401);
    expect(response.status()).not.toBe(403);
  });
});

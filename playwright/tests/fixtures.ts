/**
 * Extended Playwright fixtures with authenticated request contexts
 *
 * This module provides pre-authenticated request contexts for all test users,
 * eliminating the need for manual token management in test files.
 *
 * Usage:
 *   import { test, expect } from './fixtures';
 *
 *   test('admin can access admin endpoint', async ({ adminRequest }) => {
 *     const response = await adminRequest.get('/admin');
 *     expect(response.ok()).toBeTruthy();
 *   });
 *
 *   test('compare user access levels', async ({ authenticatedRequest }) => {
 *     const adminResp = await authenticatedRequest.admin.get('/admin');
 *     const userResp = await authenticatedRequest.user.get('/admin');
 *     expect(adminResp.ok()).toBeTruthy();
 *     expect(userResp.status()).toBe(403);
 *   });
 */

import { test as base, expect, APIRequestContext, APIResponse } from '@playwright/test';
import { getAccessToken, authHeader } from './auth-helper';
import { TEST_USERS, TestUser } from './test-users';

/**
 * Request options that can be passed to HTTP methods
 */
interface RequestOptions {
  headers?: Record<string, string>;
  data?: unknown;
  form?: Record<string, string>;
  params?: Record<string, string>;
  timeout?: number;
  failOnStatusCode?: boolean;
}

/**
 * Authenticated HTTP request context for a specific user
 */
export interface AuthenticatedContext {
  /** HTTP GET with automatic auth header */
  get(url: string, options?: RequestOptions): Promise<APIResponse>;

  /** HTTP POST with automatic auth header */
  post(url: string, options?: RequestOptions): Promise<APIResponse>;

  /** HTTP PUT with automatic auth header */
  put(url: string, options?: RequestOptions): Promise<APIResponse>;

  /** HTTP PATCH with automatic auth header */
  patch(url: string, options?: RequestOptions): Promise<APIResponse>;

  /** HTTP DELETE with automatic auth header */
  delete(url: string, options?: RequestOptions): Promise<APIResponse>;

  /** The TestUser object for this context */
  user: TestUser;

  /** Raw JWT access token */
  token: string;
}

/**
 * Collection of authenticated contexts for all test users
 */
export type AuthenticatedRequestCollection = {
  [K in keyof typeof TEST_USERS]: AuthenticatedContext;
};

/**
 * Create an authenticated request wrapper for a user
 *
 * @param request - Playwright's raw request context
 * @param token - JWT access token
 * @param user - TestUser object
 * @returns AuthenticatedContext with all HTTP methods
 */
function createAuthenticatedContext(
  request: APIRequestContext,
  token: string,
  user: TestUser
): AuthenticatedContext {
  const makeRequest =
    (method: 'get' | 'post' | 'put' | 'patch' | 'delete') =>
    (url: string, options: RequestOptions = {}): Promise<APIResponse> => {
      return request[method](url, {
        ...options,
        headers: {
          ...authHeader(token),
          ...options.headers,
        },
      });
    };

  return {
    get: makeRequest('get'),
    post: makeRequest('post'),
    put: makeRequest('put'),
    patch: makeRequest('patch'),
    delete: makeRequest('delete'),
    user,
    token,
  };
}

/**
 * Extended test fixtures with authenticated request contexts
 */
export const test = base.extend<{
  /** All authenticated request contexts */
  authenticatedRequest: AuthenticatedRequestCollection;

  /** Admin user request context */
  adminRequest: AuthenticatedContext;

  /** Standard user request context */
  userRequest: AuthenticatedContext;

  /** Read-only user request context */
  readOnlyRequest: AuthenticatedContext;

  /** Manager user request context */
  managerRequest: AuthenticatedContext;
}>({
  /**
   * Provides authenticated request contexts for all test users
   *
   * Each context includes get, post, put, patch, delete methods
   * that automatically include the Authorization header.
   */
  authenticatedRequest: async ({ request }, use) => {
    const contexts: Record<string, AuthenticatedContext> = {};

    // Authenticate all users in parallel for better performance
    const entries = Object.entries(TEST_USERS);
    const results = await Promise.allSettled(
      entries.map(async ([key, user]) => {
        const token = await getAccessToken(request, user.username, user.password);
        return { key, token, user };
      })
    );

    // Process results and handle any failures
    const failures: string[] = [];
    for (const result of results) {
      if (result.status === 'fulfilled') {
        const { key, token, user } = result.value;
        contexts[key] = createAuthenticatedContext(request, token, user);
      } else {
        failures.push(result.reason.message);
      }
    }

    // If any authentication failed, provide actionable error
    if (failures.length > 0) {
      throw new Error(
        `Failed to authenticate test users:\n${failures.join('\n')}\n\n` +
          `Ensure Keycloak is running and the realm is configured:\n` +
          `  1. Start services: docker compose up -d\n` +
          `  2. Setup realm: ./keycloak/setup-realm.sh\n` +
          `  3. Retry tests: npm test`
      );
    }

    await use(contexts as AuthenticatedRequestCollection);
  },

  /**
   * Quick access to admin-authenticated request context
   */
  adminRequest: async ({ authenticatedRequest }, use) => {
    await use(authenticatedRequest.admin);
  },

  /**
   * Quick access to standard user-authenticated request context
   */
  userRequest: async ({ authenticatedRequest }, use) => {
    await use(authenticatedRequest.user);
  },

  /**
   * Quick access to read-only user-authenticated request context
   */
  readOnlyRequest: async ({ authenticatedRequest }, use) => {
    await use(authenticatedRequest.readOnly);
  },

  /**
   * Quick access to manager-authenticated request context
   */
  managerRequest: async ({ authenticatedRequest }, use) => {
    await use(authenticatedRequest.manager);
  },
});

// Re-export expect for convenience
export { expect };

/**
 * Authentication helper for Playwright API tests
 * Provides functions to obtain JWT tokens from Keycloak using OAuth 2.0 password grant
 *
 * Future Migration Path:
 * This module uses the password grant for simplicity. When migrating to Token Exchange:
 * 1. Replace getAccessToken() implementation with token exchange logic
 * 2. The interface (function signatures) remains unchanged
 * 3. Test code does not need to be modified
 */

import { APIRequestContext } from '@playwright/test';
import { TEST_USERS, TestUser } from './test-users';

// Configuration with environment variable overrides
export const KEYCLOAK_URL = process.env.KEYCLOAK_URL || 'http://keycloak.localtest.me:8080';
export const KEYCLOAK_REALM = process.env.KEYCLOAK_REALM || 'knowledge-mapper-dev';
const CLIENT_ID = 'knowledge-mapper-backend';
const CLIENT_SECRET = 'knowledge-mapper-backend-secret';

/**
 * Token response from Keycloak
 */
interface TokenResponse {
  access_token: string;
  expires_in: number;
  refresh_token?: string;
  token_type: string;
}

/**
 * Error response from Keycloak
 */
interface ErrorResponse {
  error: string;
  error_description?: string;
}

/**
 * Cached token entry with expiration tracking
 */
interface CachedToken {
  token: string;
  expiresAt: number;
}

/**
 * Authentication strategy interface for future Token Exchange migration
 */
export interface AuthStrategy {
  getToken(request: APIRequestContext, username: string, password: string): Promise<string>;
}

/**
 * Token cache to avoid repeated authentication requests
 * Key format: "username:password" (hashed in production, plain for tests)
 */
const tokenCache = new Map<string, CachedToken>();

/**
 * Cache buffer time in milliseconds (30 seconds)
 * Tokens are refreshed this amount of time before actual expiration
 */
const CACHE_BUFFER_MS = 30 * 1000;

/**
 * Generate cache key for a username/password combination
 */
function getCacheKey(username: string, password: string): string {
  return `${username}:${password}`;
}

/**
 * Check if a cached token is still valid
 */
function isTokenValid(cached: CachedToken | undefined): cached is CachedToken {
  if (!cached) return false;
  return Date.now() < cached.expiresAt - CACHE_BUFFER_MS;
}

/**
 * Clear all cached tokens (useful for test cleanup)
 */
export function clearTokenCache(): void {
  tokenCache.clear();
}

/**
 * Password Grant authentication strategy (current implementation)
 */
class PasswordGrantStrategy implements AuthStrategy {
  async getToken(request: APIRequestContext, username: string, password: string): Promise<string> {
    // Check cache first
    const cacheKey = getCacheKey(username, password);
    const cached = tokenCache.get(cacheKey);

    if (isTokenValid(cached)) {
      return cached.token;
    }

    const tokenUrl = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`;

    const response = await request.post(tokenUrl, {
      form: {
        username,
        password,
        grant_type: 'password',
        client_id: CLIENT_ID,
        client_secret: CLIENT_SECRET,
      },
    });

    if (!response.ok()) {
      const text = await response.text();
      let errorMessage = `Failed to get token for '${username}': ${response.status()}`;

      try {
        const errorData: ErrorResponse = JSON.parse(text);
        errorMessage += ` - ${errorData.error}: ${errorData.error_description || 'No description'}`;
      } catch {
        errorMessage += ` - ${text}`;
      }

      throw new Error(errorMessage);
    }

    const data: TokenResponse = await response.json();

    // Cache the token with expiration time
    tokenCache.set(cacheKey, {
      token: data.access_token,
      expiresAt: Date.now() + data.expires_in * 1000,
    });

    return data.access_token;
  }
}

// Default authentication strategy
const authStrategy: AuthStrategy = new PasswordGrantStrategy();

/**
 * Get an access token from Keycloak for a user
 *
 * @param request - Playwright APIRequestContext
 * @param username - Keycloak username
 * @param password - User password
 * @returns Promise resolving to JWT access token string
 * @throws Error if authentication fails
 *
 * @example
 * const token = await getAccessToken(request, 'admin', 'admin123');
 */
export async function getAccessToken(
  request: APIRequestContext,
  username: string,
  password: string
): Promise<string> {
  return authStrategy.getToken(request, username, password);
}

/**
 * Get token for admin user (convenience function)
 *
 * @param request - Playwright APIRequestContext
 * @returns Promise resolving to admin JWT access token
 */
export async function getAdminToken(request: APIRequestContext): Promise<string> {
  const adminUser = TEST_USERS.admin;
  return getAccessToken(request, adminUser.username, adminUser.password);
}

/**
 * Get token for standard test user (convenience function)
 *
 * @param request - Playwright APIRequestContext
 * @returns Promise resolving to test user JWT access token
 */
export async function getTestUserToken(request: APIRequestContext): Promise<string> {
  const testUser = TEST_USERS.user;
  return getAccessToken(request, testUser.username, testUser.password);
}

/**
 * Get token for a specific test user by key
 *
 * @param request - Playwright APIRequestContext
 * @param userKey - Key from TEST_USERS (admin, user, readOnly, newUser, manager, serviceAccount)
 * @returns Promise resolving to JWT access token for the specified user
 * @throws Error if userKey is not found in TEST_USERS
 *
 * @example
 * const token = await getTokenForUser(request, 'manager');
 * const readOnlyToken = await getTokenForUser(request, 'readOnly');
 */
export async function getTokenForUser(
  request: APIRequestContext,
  userKey: keyof typeof TEST_USERS
): Promise<string> {
  const user: TestUser | undefined = TEST_USERS[userKey];

  if (!user) {
    throw new Error(
      `Unknown test user key: '${userKey}'. Available keys: ${Object.keys(TEST_USERS).join(', ')}`
    );
  }

  return getAccessToken(request, user.username, user.password);
}

/**
 * Create Authorization header object with Bearer token
 *
 * @param token - JWT access token
 * @returns Object with Authorization header
 *
 * @example
 * const headers = authHeader(token);
 * await request.get('/protected', { headers });
 */
export function authHeader(token: string): { Authorization: string } {
  return {
    Authorization: `Bearer ${token}`,
  };
}

/**
 * Get authenticated headers for a specific test user
 * Combines getTokenForUser and authHeader into a single call
 *
 * @param request - Playwright APIRequestContext
 * @param userKey - Key from TEST_USERS
 * @returns Promise resolving to headers object with Authorization
 *
 * @example
 * const headers = await getAuthHeadersForUser(request, 'admin');
 * await request.get('/admin-only', { headers });
 */
export async function getAuthHeadersForUser(
  request: APIRequestContext,
  userKey: keyof typeof TEST_USERS
): Promise<{ Authorization: string }> {
  const token = await getTokenForUser(request, userKey);
  return authHeader(token);
}

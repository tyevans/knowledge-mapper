/**
 * Test user definitions for Playwright API tests
 *
 * These users must be created in Keycloak by the setup-realm.sh script.
 * The credentials and roles defined here must match the Keycloak configuration.
 *
 * User Naming Convention:
 * - Keys are camelCase for JavaScript convention
 * - Usernames are lowercase or hyphenated for Keycloak compatibility
 *
 * Password Convention:
 * - Pattern: username + '123' for easy memorization
 * - Exception: 'testuser' uses 'test123' for brevity
 */

/**
 * Represents a test user configured in Keycloak
 */
export interface TestUser {
  /** Keycloak username for authentication */
  username: string;

  /** User password (plaintext - development only) */
  password: string;

  /** User email address */
  email: string;

  /** Array of realm roles assigned to this user */
  roles: string[];

  /** Human-readable description of the user's purpose */
  description: string;
}

/**
 * Collection of all test users
 * Keys are used as fixture names (e.g., authenticatedRequest.admin)
 */
export const TEST_USERS: Record<string, TestUser> = {
  /**
   * Admin user with full administrative access
   * Use for testing admin-only endpoints and privileged operations
   */
  admin: {
    username: 'admin',
    password: 'admin123',
    email: 'admin@example.com',
    roles: ['user', 'admin'],
    description: 'Full admin access for privileged operations',
  },

  /**
   * Standard user with basic permissions
   * Use for testing typical authenticated user flows
   */
  user: {
    username: 'testuser',
    password: 'test123',
    email: 'test@example.com',
    roles: ['user'],
    description: 'Standard user for typical authenticated flows',
  },

  /**
   * Read-only user for access control testing
   * Use for testing read-only permissions and denied write operations
   */
  readOnly: {
    username: 'readonly',
    password: 'readonly123',
    email: 'readonly@example.com',
    roles: ['user', 'readonly'],
    description: 'Read-only access for viewing without modification',
  },

  /**
   * Fresh user account for onboarding testing
   * Use for testing first-time user experiences and onboarding flows
   */
  newUser: {
    username: 'newuser',
    password: 'newuser123',
    email: 'newuser@example.com',
    roles: ['user'],
    description: 'Fresh account for onboarding flow tests',
  },

  /**
   * Manager user with elevated permissions
   * Use for testing manager-level operations without full admin access
   */
  manager: {
    username: 'manager',
    password: 'manager123',
    email: 'manager@example.com',
    roles: ['user', 'manager'],
    description: 'Elevated permissions for management operations',
  },

  /**
   * Service account for API-to-API testing
   * Use for testing service-to-service communication patterns
   * Note: Does NOT have 'user' role - only 'service' role
   */
  serviceAccount: {
    username: 'service-account',
    password: 'service123',
    email: 'service@example.com',
    roles: ['service'],
    description: 'Service account for API-to-API integration tests',
  },
};

/**
 * Find the first user that has a specific role
 *
 * @param role - Role name to search for
 * @returns TestUser object or undefined if no user has the role
 *
 * @example
 * const adminUser = getUserByRole('admin');
 * // Returns the 'admin' user
 *
 * @example
 * const serviceUser = getUserByRole('service');
 * // Returns the 'serviceAccount' user
 */
export function getUserByRole(role: string): TestUser | undefined {
  return Object.values(TEST_USERS).find((user) => user.roles.includes(role));
}

/**
 * Find all users that have a specific role
 *
 * @param role - Role name to search for
 * @returns Array of TestUser objects (empty if no users have the role)
 *
 * @example
 * const usersWithUserRole = getUsersByRole('user');
 * // Returns [admin, user, readOnly, newUser, manager] (5 users)
 *
 * @example
 * const admins = getUsersByRole('admin');
 * // Returns [admin] (1 user)
 */
export function getUsersByRole(role: string): TestUser[] {
  return Object.values(TEST_USERS).filter((user) => user.roles.includes(role));
}

/**
 * Get all test users as an array
 *
 * @returns Array of all TestUser objects
 *
 * @example
 * const allUsers = getAllUsers();
 * // Returns array of 6 users
 */
export function getAllUsers(): TestUser[] {
  return Object.values(TEST_USERS);
}

/**
 * Get a specific user by key
 *
 * @param key - User key (admin, user, readOnly, newUser, manager, serviceAccount)
 * @returns TestUser object or undefined if key doesn't exist
 *
 * @example
 * const admin = getUser('admin');
 */
export function getUser(key: keyof typeof TEST_USERS): TestUser {
  return TEST_USERS[key];
}

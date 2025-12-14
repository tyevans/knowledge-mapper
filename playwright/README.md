# Playwright API Testing

This directory contains the API testing infrastructure for Knowledge Mapper, built on [Playwright](https://playwright.dev/docs/api-testing).

## Overview

The API testing framework provides:
- **Pre-authenticated request contexts** for all test users
- **TypeScript support** for type-safe test development
- **Fixture-based patterns** for clean, maintainable tests
- **Role-based testing** for RBAC validation
- **Integration with Keycloak** for OAuth 2.0 authentication

## Prerequisites

Before running tests, ensure you have:

1. **Node.js 18+** installed
2. **Docker** and **Docker Compose** running
3. **Backend services** started (`make docker-up`)
4. **Keycloak realm** configured (`make keycloak-setup`)

## Quick Start

```bash
# 1. Install dependencies
make test-install

# 2. Start services (if not already running)
make docker-up

# 3. Setup Keycloak (if first time)
make keycloak-setup

# 4. Run tests
make test-api

# 5. View report
make test-report
```

## Project Structure

```
playwright/
├── playwright.config.ts    # Playwright configuration
├── package.json            # Dependencies and npm scripts
├── tsconfig.json           # TypeScript configuration
├── README.md               # This file
├── QUICK_START.md          # 5-minute getting started guide
└── tests/
    ├── auth-helper.ts      # Keycloak authentication utilities
    ├── test-users.ts       # Test user definitions
    ├── fixtures.ts         # Extended Playwright fixtures
    ├── api-endpoints.api.spec.ts      # Basic tests (manual auth)
    └── api-with-fixtures.api.spec.ts  # Fixture-based tests (recommended)
```

## Writing Tests

### Recommended Pattern: Using Fixtures

The fixture pattern is the **recommended approach** for writing API tests. Fixtures automatically handle authentication, providing pre-configured request contexts for each test user.

```typescript
import { test, expect } from './fixtures';

test('admin can access admin endpoint', async ({ adminRequest }) => {
  const response = await adminRequest.get('//api/v1/test/admin');

  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  expect(data.user.username).toBe('admin');
  expect(data.user.roles).toContain('admin');
});

test('regular user cannot access admin endpoint', async ({ userRequest }) => {
  const response = await userRequest.get('//api/v1/test/admin');

  expect(response.status()).toBe(403);
});
```

### Multi-User Testing

For tests that need to compare access levels between users:

```typescript
test('compare admin and user access', async ({ authenticatedRequest }) => {
  // Admin can access
  const adminResp = await authenticatedRequest.admin.get('//api/v1/test/admin');
  expect(adminResp.ok()).toBeTruthy();

  // User cannot access
  const userResp = await authenticatedRequest.user.get('//api/v1/test/admin');
  expect(userResp.status()).toBe(403);
});
```

### Accessing User Metadata

Fixtures provide access to user information and tokens:

```typescript
test('can access user info', async ({ adminRequest }) => {
  // User metadata
  console.log(adminRequest.user.username);  // 'admin'
  console.log(adminRequest.user.roles);     // ['user', 'admin']
  console.log(adminRequest.user.email);     // 'admin@example.com'

  // Raw JWT token (for custom scenarios)
  const token = adminRequest.token;
});
```

### Advanced Pattern: Manual Authentication

For custom authentication scenarios or testing invalid tokens:

```typescript
import { test, expect } from '@playwright/test';
import { getAccessToken, authHeader } from './auth-helper';

test('custom auth scenario', async ({ request }) => {
  const token = await getAccessToken(request, 'admin', 'admin123');
  const response = await request.get('//api/v1/auth/me', {
    headers: {
      ...authHeader(token),
      'X-Custom-Header': 'custom-value',
    },
  });

  expect(response.ok()).toBeTruthy();
});
```

## Available Fixtures

| Fixture | User | Roles | Description |
|---------|------|-------|-------------|
| `adminRequest` | admin | user, admin | Full administrative access |
| `userRequest` | testuser | user | Standard authenticated user |
| `readOnlyRequest` | readonly | user, readonly | Read-only access |
| `managerRequest` | manager | user, manager | Elevated permissions |
| `authenticatedRequest` | All users | Various | Access to all user contexts |

### authenticatedRequest Properties

The `authenticatedRequest` fixture provides access to all users:

| Property | User | Roles |
|----------|------|-------|
| `.admin` | admin | user, admin |
| `.user` | testuser | user |
| `.readOnly` | readonly | user, readonly |
| `.newUser` | newuser | user |
| `.manager` | manager | user, manager |
| `.serviceAccount` | service-account | service |

## Test Users

All test users are created in Keycloak by the `setup-realm.sh` script.

| Username | Password | Email | Roles | Use Case |
|----------|----------|-------|-------|----------|
| admin | admin123 | admin@example.com | user, admin | Admin-only endpoints |
| testuser | test123 | test@example.com | user | Standard user flows |
| readonly | readonly123 | readonly@example.com | user, readonly | Read-only access testing |
| newuser | newuser123 | newuser@example.com | user | Onboarding flows |
| manager | manager123 | manager@example.com | user, manager | Elevated access testing |
| service-account | service123 | service@example.com | service | API-to-API integration |

## Running Tests

### npm Scripts

```bash
npm test              # Run all tests
npm run test:api      # Run API tests only
npm run test:ui       # Interactive UI mode
npm run test:debug    # Debug mode
npm run report        # Open HTML report
```

### Makefile Targets

```bash
make test             # Run all tests
make test-api         # Run API tests only
make test-ui          # Interactive UI mode
make test-debug       # Debug mode
make test-report      # Open HTML report
make test-install     # Install dependencies
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_URL` | `http://localhost:8000` | Backend API base URL |
| `KEYCLOAK_URL` | `http://localhost:8080` | Keycloak server URL |
| `KEYCLOAK_REALM` | `knowledge-mapper-dev` | Keycloak realm name |
| `CI` | undefined | Set to `true` in CI environments |

### CI/CD Behavior

When `CI=true`:
- Single worker for test stability
- 2 retries on failure
- No webServer auto-start (services must be pre-started)
- `.only()` tests cause failure

## Troubleshooting

### Common Issues

#### "Failed to get token for 'admin': 401"

**Cause:** Keycloak not configured or user doesn't exist.

**Solution:**
```bash
make keycloak-setup
```

#### "Connection refused"

**Cause:** Backend or Keycloak not running.

**Solution:**
```bash
make docker-up
make keycloak-wait
```

#### "Role 'admin' required"

**Cause:** Using wrong user for admin-only endpoint.

**Solution:** Use `adminRequest` fixture instead of `userRequest`.

#### Tests pass locally but fail in CI

**Cause:** Services not ready when tests start.

**Solution:** Add health check wait before running tests:
```bash
make keycloak-wait
```

### Debug Mode

For debugging failing tests:

```bash
# Run in debug mode (pause on failure)
make test-debug

# Run in UI mode (interactive)
make test-ui

# Run single test file
cd playwright && npx playwright test tests/api-endpoints.api.spec.ts
```

### View Test Report

After running tests, view the HTML report:

```bash
make test-report
```

## API Endpoints

Tests target these backend endpoints:

| Endpoint | Method | Auth Required | Role Required |
|----------|--------|---------------|---------------|
| `/` | GET | No | - |
| `//api/v1/health` | GET | No | - |
| `//api/v1/auth/me` | GET | Yes | Any |
| `//api/v1/test/protected` | GET | Yes | Any |
| `//api/v1/test/admin` | GET | Yes | admin |

## Contributing

When adding new tests:

1. Use the fixture pattern (`import { test } from './fixtures'`)
2. Name files with `.api.spec.ts` extension
3. Group related tests in `test.describe()` blocks
4. Include both positive and negative test cases
5. Add JSDoc comments for complex scenarios

## Further Reading

- [Playwright API Testing Guide](https://playwright.dev/docs/api-testing)
- [Playwright Fixtures](https://playwright.dev/docs/test-fixtures)
- [Project CLAUDE.md](../CLAUDE.md) for backend patterns

# Quick Start - Playwright API Testing

Get your first API test running in under 5 minutes.

## Prerequisites

- Docker running
- Node.js 18+ installed

## Step 1: Install Dependencies

```bash
make test-install
```

Or without Make:
```bash
cd playwright && npm install
```

## Step 2: Start Services

```bash
make docker-up
```

Wait for services to be ready (about 30 seconds).

## Step 3: Setup Keycloak

```bash
make keycloak-setup
```

This creates test users in Keycloak.

## Step 4: Run Tests

```bash
make test-api
```

Expected output: All tests pass!

## Step 5: View Report

```bash
make test-report
```

Opens an HTML report in your browser.

---

## Write Your First Test

Create a new file `tests/my-first.api.spec.ts`:

```typescript
import { test, expect } from './fixtures';

test('my first API test', async ({ userRequest }) => {
  // Make an authenticated request
  const response = await userRequest.get('//api/v1/auth/me');

  // Verify the response
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  expect(data.username).toBe('testuser');
});
```

Run your test:
```bash
cd playwright && npx playwright test tests/my-first.api.spec.ts
```

---

## Quick Reference: Available Fixtures

| Fixture | User | Quick Description |
|---------|------|-------------------|
| `adminRequest` | admin | Full admin access |
| `userRequest` | testuser | Standard user |
| `readOnlyRequest` | readonly | Read-only access |
| `managerRequest` | manager | Elevated access |
| `authenticatedRequest` | All | Access all users |

## Quick Reference: Test Users

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | Admin |
| testuser | test123 | User |
| readonly | readonly123 | Read-only |
| manager | manager123 | Manager |

---

## Common Commands

| Command | Description |
|---------|-------------|
| `make test` | Run all tests |
| `make test-api` | Run API tests |
| `make test-ui` | Interactive mode |
| `make test-debug` | Debug mode |
| `make test-report` | View report |

---

## Debugging Tips

### Interactive UI Mode
```bash
make test-ui
```
Opens Playwright's interactive test runner.

### Debug a Failing Test
```bash
make test-debug
```
Pauses execution on failure for inspection.

### Run a Single Test
```bash
cd playwright && npx playwright test tests/my-test.api.spec.ts
```

---

## Next Steps

- Read the full [README](./README.md) for advanced patterns
- Explore example tests in `tests/api-with-fixtures.api.spec.ts`
- Learn about multi-user testing with `authenticatedRequest`

---

*Need help? Check the [Troubleshooting section](./README.md#troubleshooting) in the README.*

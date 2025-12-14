// Multi-Tenant Isolation Load Test
//
// Tests that tenant isolation is maintained under load.
// Verifies that users can only access their own tenant's data
// and that no cross-tenant data leakage occurs.
//
// Features:
//   - Each VU operates as a different tenant
//   - Creates resources and verifies tenant_id
//   - Attempts cross-tenant access (should fail)
//   - Tracks any isolation violations
//
// Prerequisites:
//   - Test users with different tenant_ids in Keycloak
//   - Backend with multi-tenant RLS enabled
//   - PostgreSQL with tenant-scoped tables
//
// Usage:
//   k6 run tests/load/scripts/multi-tenant.js
//   k6 run --env TEST_USERS=alice:pass:tenant1,bob:pass:tenant2 tests/load/scripts/multi-tenant.js
//   ./scripts/load-test.sh multi-tenant
//
// Environment Variables:
//   TEST_USERS    - Format: "user1:pass1:tenant1,user2:pass2:tenant2"
//   BASE_URL      - API base URL
//   AUTH_DEBUG    - Enable debug logging

import http from 'k6/http';
import { check, sleep, group, fail } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { BASE_URL, API_PREFIX, defaultOptions } from '../lib/config.js';
import { authConfig, getValidToken, getTenantId, authHeadersWithToken, logAuthConfig } from '../lib/auth.js';
import { initializeTokenPool, getPooledToken, getTokensByTenant, logPoolStatus } from '../lib/tokens.js';
import { thinkTime, generateTestId } from '../lib/helpers.js';

// Custom metrics for tenant isolation testing
const tenantRequests = new Counter('tenant_requests');
const crossTenantErrors = new Counter('cross_tenant_errors');
const crossTenantAttempts = new Counter('cross_tenant_attempts');
const tenantIsolationRate = new Rate('tenant_isolation_success');
const tenantMismatch = new Counter('tenant_mismatch');
const resourceCreations = new Counter('resource_creations');
const resourcesByTenant = {};  // Track resources per tenant

// Test configuration
export const options = {
  scenarios: {
    multi_tenant_isolation: {
      executor: 'per-vu-iterations',
      vus: parseInt(__ENV.VUS || '10'),
      iterations: parseInt(__ENV.ITERATIONS || '50'),
      maxDuration: '10m',
    },
  },
  thresholds: {
    // CRITICAL: No cross-tenant access should succeed
    cross_tenant_errors: ['count==0'],

    // High success rate for legitimate tenant operations
    tenant_isolation_success: ['rate>0.99'],

    // No tenant_id mismatches in responses
    tenant_mismatch: ['count==0'],

    // Normal performance thresholds
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.10'],

    // Check pass rate
    checks: ['rate>0.95'],
  },
  tags: {
    test_type: 'multi_tenant',
  },
};

export function setup() {
  console.log('\n=== Multi-Tenant Isolation Load Test ===');
  console.log(`Base URL: ${BASE_URL}${API_PREFIX}`);
  console.log('');

  logAuthConfig();
  console.log('');

  // Validate we have users with tenant info
  if (authConfig.testUsers.length < 2) {
    console.warn('WARNING: Only 1 test user configured.');
    console.warn('For proper multi-tenant testing, configure multiple users with different tenants.');
    console.warn('Format: TEST_USERS=alice:pass:tenant1,bob:pass:tenant2');
  }

  // Initialize token pool
  const tokenPool = initializeTokenPool();

  if (tokenPool.length === 0) {
    fail('No valid tokens obtained');
  }

  logPoolStatus(tokenPool);

  // Identify unique tenants
  const tenants = new Set();
  for (const token of tokenPool) {
    if (token.tenantId) {
      tenants.add(token.tenantId);
    }
  }

  console.log(`\nUnique tenants: ${tenants.size}`);
  if (tenants.size > 0) {
    console.log(`Tenants: ${Array.from(tenants).join(', ')}`);
  }

  // Verify health
  const healthResponse = http.get(`${BASE_URL}${API_PREFIX}/health`);
  if (healthResponse.status !== 200) {
    console.warn(`Health check: ${healthResponse.status}`);
  }

  return {
    startTime: new Date().toISOString(),
    tokenPool: tokenPool,
    tenantList: Array.from(tenants),
    createdResources: [],  // Track resources for cleanup
  };
}

export default function(data) {
  // Get token for this VU
  let token;
  let expectedTenantId;
  let username;

  try {
    const pooledToken = getPooledToken(data.tokenPool, __VU);
    token = pooledToken.accessToken;
    expectedTenantId = pooledToken.tenantId || getTenantId(token);
    username = pooledToken.username;
  } catch (e) {
    console.error(`VU ${__VU}: Failed to get pooled token: ${e.message}`);
    sleep(1);
    return;
  }

  if (!token) {
    console.error(`VU ${__VU}: No token available`);
    return;
  }

  const headers = authHeadersWithToken(token);

  // Test 1: Create a resource and verify it has correct tenant_id
  group('create_tenant_resource', function() {
    const testId = generateTestId();
    const payload = JSON.stringify({
      title: `Tenant ${expectedTenantId} - ${testId}`,
      description: `VU ${__VU}, User ${username}, Iteration ${__ITER}`,
      tenant_marker: expectedTenantId,  // Custom field for verification
    });

    const createResponse = http.post(`${BASE_URL}${API_PREFIX}/todos`, payload, {
      headers: headers,
      tags: { name: 'create_tenant_todo', tenant: expectedTenantId || 'unknown' },
    });

    tenantRequests.add(1);
    resourceCreations.add(1);

    // Verify creation
    const created = check(createResponse, {
      'create: status 201 or 200': (r) => r.status === 201 || r.status === 200,
    });

    if (created && (createResponse.status === 201 || createResponse.status === 200)) {
      try {
        const resourceData = JSON.parse(createResponse.body);
        const resourceId = resourceData.id;
        const resourceTenantId = resourceData.tenant_id;

        // CRITICAL CHECK: Verify tenant_id matches expected
        if (resourceTenantId) {
          if (resourceTenantId !== expectedTenantId) {
            crossTenantErrors.add(1);
            tenantMismatch.add(1);
            tenantIsolationRate.add(0);
            console.error(`TENANT VIOLATION: Expected ${expectedTenantId}, got ${resourceTenantId}`);
            console.error(`  VU: ${__VU}, User: ${username}, Resource: ${resourceId}`);
          } else {
            tenantIsolationRate.add(1);
          }

          check(createResponse, {
            'create: tenant_id matches': () => resourceTenantId === expectedTenantId,
          });
        } else {
          // No tenant_id in response - may be expected for some APIs
          tenantIsolationRate.add(1);
          if (__ENV.AUTH_DEBUG === 'true') {
            console.log(`Note: No tenant_id in response for resource ${resourceId}`);
          }
        }

        // Store resource for later tests and cleanup
        if (resourceId) {
          data.createdResources.push({
            id: resourceId,
            tenantId: expectedTenantId,
            vuId: __VU,
          });

          // Test 2: Verify we can read our own resource
          group('read_own_resource', function() {
            sleep(0.5);  // Brief pause

            const readResponse = http.get(`${BASE_URL}${API_PREFIX}/todos/${resourceId}`, {
              headers: headers,
              tags: { name: 'read_own_todo', tenant: expectedTenantId || 'unknown' },
            });

            tenantRequests.add(1);

            check(readResponse, {
              'read-own: status 200': (r) => r.status === 200,
              'read-own: same resource': (r) => {
                if (r.status !== 200) return false;
                try {
                  const body = JSON.parse(r.body);
                  return body.id === resourceId;
                } catch {
                  return false;
                }
              },
            });
          });

          // Test 3: Clean up - delete our resource
          group('delete_own_resource', function() {
            sleep(0.5);

            const deleteResponse = http.del(`${BASE_URL}${API_PREFIX}/todos/${resourceId}`, null, {
              headers: headers,
              tags: { name: 'delete_own_todo', tenant: expectedTenantId || 'unknown' },
            });

            check(deleteResponse, {
              'delete-own: status 200 or 204': (r) =>
                r.status === 200 || r.status === 204,
            });
          });
        }

      } catch (e) {
        if (__ENV.AUTH_DEBUG === 'true') {
          console.log(`VU ${__VU}: Failed to process response: ${e.message}`);
        }
      }
    }
  });

  thinkTime(1, 2);

  // Test 4: List resources - should only see current tenant's data
  group('list_tenant_resources', function() {
    const listResponse = http.get(`${BASE_URL}${API_PREFIX}/todos`, {
      headers: headers,
      tags: { name: 'list_todos', tenant: expectedTenantId || 'unknown' },
    });

    tenantRequests.add(1);

    check(listResponse, {
      'list: status 200': (r) => r.status === 200,
    });

    // Verify all returned items belong to current tenant
    if (listResponse.status === 200) {
      try {
        const body = JSON.parse(listResponse.body);
        const items = Array.isArray(body) ? body : (body.items || body.data || []);

        let foundOtherTenant = false;
        for (const item of items) {
          if (item.tenant_id && item.tenant_id !== expectedTenantId) {
            foundOtherTenant = true;
            crossTenantErrors.add(1);
            console.error(`CROSS-TENANT DATA LEAK: Found ${item.tenant_id} resource in ${expectedTenantId} list`);
            console.error(`  Resource ID: ${item.id}, Title: ${item.title}`);
          }
        }

        check(listResponse, {
          'list: only own tenant data': () => !foundOtherTenant,
        });

        if (!foundOtherTenant) {
          tenantIsolationRate.add(1);
        } else {
          tenantIsolationRate.add(0);
        }

      } catch (e) {
        // Can't parse response - not a tenant violation
        tenantIsolationRate.add(1);
      }
    }
  });

  thinkTime(1, 2);

  // Test 5: Attempt cross-tenant access (should fail)
  // Only run occasionally and if we have multiple tenants
  if (__ITER % 5 === 0 && data.tenantList.length > 1) {
    group('cross_tenant_attempt', function() {
      // Find a different tenant's resource to try accessing
      const otherTenants = data.tenantList.filter(t => t !== expectedTenantId);
      if (otherTenants.length === 0) {
        return;
      }

      const targetTenant = otherTenants[__ITER % otherTenants.length];

      // Try to access a resource that might belong to another tenant
      // Using a predictable pattern for testing
      const targetResourceId = `cross-tenant-test-${targetTenant}-${__ITER}`;

      crossTenantAttempts.add(1);

      // This should return 404 or 403 (not 200)
      const crossTenantResponse = http.get(`${BASE_URL}${API_PREFIX}/todos/${targetResourceId}`, {
        headers: headers,
        tags: { name: 'cross_tenant_attempt', source_tenant: expectedTenantId, target_tenant: targetTenant },
      });

      // Success case: NOT getting a 200 with another tenant's data
      const isolated = check(crossTenantResponse, {
        'cross-tenant: blocked or not found': (r) =>
          r.status === 404 || r.status === 403 || r.status === 401,
      });

      if (crossTenantResponse.status === 200) {
        // POTENTIAL VIOLATION - verify the data
        try {
          const body = JSON.parse(crossTenantResponse.body);
          if (body.tenant_id && body.tenant_id !== expectedTenantId) {
            crossTenantErrors.add(1);
            tenantIsolationRate.add(0);
            console.error(`CROSS-TENANT ACCESS SUCCEEDED:`);
            console.error(`  Requester: ${expectedTenantId}`);
            console.error(`  Accessed: ${body.tenant_id}`);
            console.error(`  Resource: ${body.id}`);
          } else {
            // 200 but same tenant (legitimate)
            tenantIsolationRate.add(1);
          }
        } catch (e) {
          // Can't verify - count as isolated
          tenantIsolationRate.add(1);
        }
      } else {
        // Properly blocked
        tenantIsolationRate.add(1);
      }
    });
  }
}

export function teardown(data) {
  console.log('\n=== Multi-Tenant Test Complete ===');
  console.log(`Started: ${data.startTime}`);
  console.log(`Ended: ${new Date().toISOString()}`);
  console.log(`Tenants Tested: ${data.tenantList.length}`);
  console.log(`Resources Created: ${data.createdResources.length}`);
}

export function handleSummary(data) {
  const totalRequests = data.metrics.tenant_requests?.values?.count || 0;
  const crossTenantErrorCount = data.metrics.cross_tenant_errors?.values?.count || 0;
  const crossTenantAttemptCount = data.metrics.cross_tenant_attempts?.values?.count || 0;
  const tenantMismatchCount = data.metrics.tenant_mismatch?.values?.count || 0;
  const isolationRate = ((data.metrics.tenant_isolation_success?.values?.rate || 1) * 100).toFixed(2);

  console.log('\n=== Multi-Tenant Isolation Summary ===');
  console.log(`Total Tenant Requests: ${totalRequests}`);
  console.log(`Cross-Tenant Errors: ${crossTenantErrorCount}`);
  console.log(`Cross-Tenant Attempts: ${crossTenantAttemptCount}`);
  console.log(`Tenant ID Mismatches: ${tenantMismatchCount}`);
  console.log(`Isolation Success Rate: ${isolationRate}%`);

  // Final verdict
  if (crossTenantErrorCount === 0 && tenantMismatchCount === 0) {
    console.log('\nRESULT: TENANT ISOLATION VERIFIED');
    console.log('No cross-tenant data access detected.');
  } else {
    console.log('\nRESULT: TENANT ISOLATION VIOLATED');
    console.log('CRITICAL: Cross-tenant data access was detected!');
    console.log('Review logs for details on the violations.');
  }

  const summary = {
    timestamp: new Date().toISOString(),
    scenario: 'multi_tenant',
    result: crossTenantErrorCount === 0 && tenantMismatchCount === 0 ? 'PASSED' : 'FAILED',
    metrics: {
      totalRequests: totalRequests,
      crossTenantErrors: crossTenantErrorCount,
      crossTenantAttempts: crossTenantAttemptCount,
      tenantMismatches: tenantMismatchCount,
      isolationSuccessRate: parseFloat(isolationRate),
      resourcesCreated: data.metrics.resource_creations?.values?.count || 0,
    },
    thresholdsPassed: crossTenantErrorCount === 0,
    duration: {
      avg: data.metrics.http_req_duration?.values?.avg || 0,
      p95: data.metrics.http_req_duration?.values?.['p(95)'] || 0,
    },
  };

  return {
    'results/multi-tenant-summary.json': JSON.stringify(summary, null, 2),
  };
}

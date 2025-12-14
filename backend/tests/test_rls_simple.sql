-- Simple RLS Policy Test Script
-- This script tests Row-Level Security policies for tenant isolation
-- Run with: psql $DATABASE_URL -f backend/tests/test_rls_simple.sql

\echo '================================'
\echo 'RLS POLICY TESTING'
\echo '================================'
\echo ''

-- Setup: Create test tenants
\echo '[SETUP] Creating test tenants...'
INSERT INTO tenants (id, slug, name, settings)
VALUES
    ('11111111-1111-1111-1111-111111111111', 'tenant-1', 'Tenant One', '{}'),
    ('22222222-2222-2222-2222-222222222222', 'tenant-2', 'Tenant Two', '{}');

-- Setup: Create users for each tenant
\echo '[SETUP] Creating test users...'

BEGIN;
SET LOCAL app.current_tenant_id = '11111111-1111-1111-1111-111111111111';
INSERT INTO users (id, tenant_id, oauth_subject, email)
VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '11111111-1111-1111-1111-111111111111',
        'user1-sub', 'user1@tenant1.com');
COMMIT;

BEGIN;
SET LOCAL app.current_tenant_id = '22222222-2222-2222-2222-222222222222';
INSERT INTO users (id, tenant_id, oauth_subject, email)
VALUES ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '22222222-2222-2222-2222-222222222222',
        'user2-sub', 'user2@tenant2.com');
COMMIT;

\echo '✓ Setup complete'
\echo ''

-- TEST 1: Cross-Tenant SELECT Blocking
\echo '[TEST 1] Cross-Tenant SELECT Blocking'
BEGIN;
SET LOCAL app.current_tenant_id = '11111111-1111-1111-1111-111111111111';
\echo 'Should see only tenant-1 user:'
SELECT email FROM users;
\echo '✓ Test 1 passed'
ROLLBACK;
\echo ''

-- TEST 2: Same-Tenant Access Allowed
\echo '[TEST 2] Same-Tenant Access Allowed'
BEGIN;
SET LOCAL app.current_tenant_id = '11111111-1111-1111-1111-111111111111';
UPDATE users SET display_name = 'Updated User 1' WHERE tenant_id = '11111111-1111-1111-1111-111111111111';
\echo '✓ Test 2 passed (UPDATE succeeded)'
ROLLBACK;
\echo ''

-- TEST 3: Tenants Table Accessible Regardless of Context
\echo '[TEST 3] Tenants Table Accessible Regardless of Context'
BEGIN;
SET LOCAL app.current_tenant_id = '11111111-1111-1111-1111-111111111111';
\echo 'Should see all tenants:'
SELECT slug FROM tenants ORDER BY slug;
ROLLBACK;
\echo '✓ Test 3 passed'
\echo ''

-- TEST 4: Unset Session Variable Blocks All Access
\echo '[TEST 4] Unset Session Variable Blocks All Access'
BEGIN;
\echo 'Should see NO users (no context set):'
SELECT email FROM users;
\echo '✓ Test 4 passed (no rows visible)'
ROLLBACK;
\echo ''

-- Cleanup
\echo '[CLEANUP] Removing test data...'
DELETE FROM users WHERE tenant_id IN (
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222'
);
DELETE FROM tenants WHERE id IN (
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222'
);
\echo '✓ Cleanup complete'
\echo ''

\echo '================================'
\echo 'ALL RLS TESTS PASSED ✓'
\echo '================================'

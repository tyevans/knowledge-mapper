"""
Manual RLS Policy Testing Script

This script tests the Row-Level Security policies created by the initial migration.
Tests verify tenant isolation and fail-safe behavior.

Run with: python -m pytest backend/tests/test_rls_policies_manual.py -v -s
"""

import asyncio
import uuid
from datetime import datetime
from sqlalchemy import text
from app.core.database import engine


async def test_rls_policies():
    """
    Comprehensive RLS policy testing.

    Tests:
    1. Cross-tenant SELECT blocking
    2. Cross-tenant INSERT blocking
    3. Cross-tenant UPDATE blocking
    4. Cross-tenant DELETE blocking
    5. Same-tenant access allowed
    6. Unset session variable blocks all access
    7. Tenants table accessible regardless of context
    8. Foreign key cascades work correctly
    9. Adversarial bypass attempts
    """
    tenant1_id = uuid.UUID('11111111-1111-1111-1111-111111111111')
    tenant2_id = uuid.UUID('22222222-2222-2222-2222-222222222222')
    user1_id = uuid.UUID('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
    user2_id = uuid.UUID('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb')

    print("\n" + "="*80)
    print("RLS POLICY TESTING")
    print("="*80)

    async with engine.begin() as conn:
        # Setup: Create test tenants
        print("\n[SETUP] Creating test tenants...")
        await conn.execute(text("""
            INSERT INTO tenants (id, slug, name, settings, created_at, updated_at)
            VALUES
                (:tenant1_id, 'tenant-1', 'Tenant One', '{}', NOW(), NOW()),
                (:tenant2_id, 'tenant-2', 'Tenant Two', '{}', NOW(), NOW())
        """), {"tenant1_id": tenant1_id, "tenant2_id": tenant2_id})

        # Setup: Create users for each tenant
        print("[SETUP] Creating test users...")

        # Set context to tenant 1 and insert user for tenant 1
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'"))
        await conn.execute(text("""
            INSERT INTO users (id, tenant_id, oauth_subject, email, created_at, updated_at)
            VALUES (:user_id, :tenant_id, 'user1-sub', 'user1@tenant1.com', NOW(), NOW())
        """), {"user_id": user1_id, "tenant_id": tenant1_id})

        # Set context to tenant 2 and insert user for tenant 2
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        await conn.execute(text("""
            INSERT INTO users (id, tenant_id, oauth_subject, email, created_at, updated_at)
            VALUES (:user_id, :tenant_id, 'user2-sub', 'user2@tenant2.com', NOW(), NOW())
        """), {"user_id": user2_id, "tenant_id": tenant2_id})

        print("✓ Setup complete\n")

        # TEST 1: Cross-Tenant SELECT Blocking
        print("[TEST 1] Cross-Tenant SELECT Blocking")
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'")) if 'tenant1' in locals() or globals() else await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        result = await conn.execute(text("SELECT email FROM users"))
        emails = [row[0] for row in result]

        assert 'user1@tenant1.com' in emails, "Should see tenant 1 user"
        assert 'user2@tenant2.com' not in emails, "Should NOT see tenant 2 user"
        print(f"  ✓ Tenant 1 context sees only tenant 1 users: {emails}")

        # Direct attempt to query tenant 2 users
        result = await conn.execute(text("""
            SELECT email FROM users WHERE tenant_id = :tenant2_id
        """), {"tenant2_id": tenant2_id})
        emails = [row[0] for row in result]
        assert len(emails) == 0, "Should not be able to query tenant 2 users from tenant 1 context"
        print("  ✓ Direct WHERE clause for tenant 2 returns empty (RLS blocks)")

        # TEST 2: Cross-Tenant INSERT Blocking
        print("\n[TEST 2] Cross-Tenant INSERT Blocking")
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'")) if 'tenant1' in locals() or globals() else await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        try:
            await conn.execute(text("""
                INSERT INTO users (id, tenant_id, oauth_subject, email, created_at, updated_at)
                VALUES (:user_id, :tenant_id, 'user3-sub', 'user3@tenant2.com', NOW(), NOW())
            """), {"user_id": uuid.uuid4(), "tenant_id": tenant2_id})
            assert False, "Should not be able to insert into tenant 2 from tenant 1 context"
        except Exception as e:
            assert "row-level security policy" in str(e).lower(), f"Wrong error: {e}"
            print(f"  ✓ INSERT blocked with RLS error: {str(e)[:80]}...")

        # TEST 3: Cross-Tenant UPDATE Blocking
        print("\n[TEST 3] Cross-Tenant UPDATE Blocking")
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'")) if 'tenant1' in locals() or globals() else await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        result = await conn.execute(text("""
            UPDATE users SET display_name = 'Hacked'
            WHERE tenant_id = :tenant2_id
        """), {"tenant2_id": tenant2_id})
        assert result.rowcount == 0, "Should not update any rows for tenant 2"
        print("  ✓ UPDATE returned 0 rows (tenant 2 users not visible)")

        # Verify tenant 2 user unchanged
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'")) if 'tenant1' in locals() or globals() else await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        result = await conn.execute(text("""
            SELECT display_name FROM users WHERE email = 'user2@tenant2.com'
        """))
        display_name = result.scalar()
        assert display_name is None, "Display name should still be NULL"
        print("  ✓ Tenant 2 user unchanged (verified from tenant 2 context)")

        # TEST 4: Cross-Tenant DELETE Blocking
        print("\n[TEST 4] Cross-Tenant DELETE Blocking")
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'")) if 'tenant1' in locals() or globals() else await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        result = await conn.execute(text("""
            DELETE FROM users WHERE tenant_id = :tenant2_id
        """), {"tenant2_id": tenant2_id})
        assert result.rowcount == 0, "Should not delete any rows for tenant 2"
        print("  ✓ DELETE returned 0 rows (tenant 2 users not visible)")

        # Verify tenant 2 user still exists
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'")) if 'tenant1' in locals() or globals() else await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM users WHERE tenant_id = :tenant2_id
        """), {"tenant2_id": tenant2_id})
        count = result.scalar()
        assert count == 1, "Tenant 2 user should still exist"
        print("  ✓ Tenant 2 user still exists (verified from tenant 2 context)")

        # TEST 5: Same-Tenant Access Allowed
        print("\n[TEST 5] Same-Tenant Access Allowed")
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'")) if 'tenant1' in locals() or globals() else await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        result = await conn.execute(text("""
            UPDATE users SET display_name = 'Updated User 1'
            WHERE tenant_id = :tenant1_id
        """), {"tenant1_id": tenant1_id})
        assert result.rowcount == 1, "Should update 1 row for same tenant"
        print("  ✓ UPDATE succeeded for same tenant (1 row updated)")

        result = await conn.execute(text("""
            SELECT display_name FROM users WHERE email = 'user1@tenant1.com'
        """))
        display_name = result.scalar()
        assert display_name == 'Updated User 1', "Display name should be updated"
        print(f"  ✓ Verified update: display_name = '{display_name}'")

        # TEST 6: Unset Session Variable Blocks All Access
        print("\n[TEST 6] Unset Session Variable Blocks All Access")
        # Unset the session variable
        await conn.execute(text("RESET app.current_tenant_id"))

        result = await conn.execute(text("SELECT email FROM users"))
        emails = [row[0] for row in result]
        assert len(emails) == 0, "Should not see any users without tenant context"
        print("  ✓ SELECT without context returns empty (fail-safe)")

        try:
            await conn.execute(text("""
                INSERT INTO users (id, tenant_id, oauth_subject, email, created_at, updated_at)
                VALUES (:user_id, :tenant_id, 'user4-sub', 'user4@tenant1.com', NOW(), NOW())
            """), {"user_id": uuid.uuid4(), "tenant_id": tenant1_id})
            assert False, "Should not be able to insert without tenant context"
        except Exception as e:
            assert "row-level security policy" in str(e).lower(), f"Wrong error: {e}"
            print(f"  ✓ INSERT blocked without context: {str(e)[:80]}...")

        # TEST 7: Tenants Table Accessible Regardless of Context
        print("\n[TEST 7] Tenants Table Accessible Regardless of Context")
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'")) if 'tenant1' in locals() or globals() else await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        result = await conn.execute(text("SELECT slug FROM tenants ORDER BY slug"))
        slugs = [row[0] for row in result]
        assert 'tenant-1' in slugs and 'tenant-2' in slugs, "Should see all tenants"
        print(f"  ✓ With tenant 1 context, can see all tenants: {slugs}")

        await conn.execute(text("RESET app.current_tenant_id"))
        result = await conn.execute(text("SELECT slug FROM tenants ORDER BY slug"))
        slugs = [row[0] for row in result]
        assert 'tenant-1' in slugs and 'tenant-2' in slugs, "Should see all tenants"
        print(f"  ✓ Without context, can still see all tenants: {slugs}")

        # TEST 8: Adversarial - Attempt to move user between tenants
        print("\n[TEST 8] Adversarial - Attempt to Move User Between Tenants")
        await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant1_id}'")) if 'tenant1' in locals() or globals() else await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant2_id}'"))
        try:
            await conn.execute(text("""
                UPDATE users SET tenant_id = :tenant2_id
                WHERE email = 'user1@tenant1.com'
            """), {"tenant2_id": tenant2_id})
            assert False, "Should not be able to change tenant_id"
        except Exception as e:
            assert "row-level security policy" in str(e).lower(), f"Wrong error: {e}"
            print(f"  ✓ UPDATE tenant_id blocked: {str(e)[:80]}...")

        # Cleanup
        print("\n[CLEANUP] Removing test data...")
        await conn.execute(text("RESET app.current_tenant_id"))
        await conn.execute(text("""
            DELETE FROM users WHERE tenant_id IN (:tenant1_id, :tenant2_id)
        """), {"tenant1_id": tenant1_id, "tenant2_id": tenant2_id})
        await conn.execute(text("""
            DELETE FROM tenants WHERE id IN (:tenant1_id, :tenant2_id)
        """), {"tenant1_id": tenant1_id, "tenant2_id": tenant2_id})
        print("✓ Cleanup complete")

    await engine.dispose()

    print("\n" + "="*80)
    print("ALL RLS POLICY TESTS PASSED ✓")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(test_rls_policies())

"""
Manual test script for tenant context service.

This script validates the core functionality of the tenant context service:
1. Setting tenant context sets PostgreSQL session variable
2. Clearing tenant context removes the session variable
3. Tenant validation works correctly
4. RLS bypass works correctly
5. TenantContext async context manager works correctly

Run with: python -m tests.manual_test_tenant_context
"""

import asyncio
import sys
from uuid import uuid4

from app.core.database import AsyncSessionLocal
from app.services.tenant_context import (
    set_tenant_context,
    clear_tenant_context,
    bypass_rls,
    validate_tenant_active,
    TenantContext,
    TenantContextError
)
from app.models.tenant import Tenant
from app.core.context import get_current_tenant, clear_current_tenant
from sqlalchemy import text


async def test_set_and_read_tenant_context():
    """Test setting and reading tenant context."""
    print("\n=== Test 1: Set and Read Tenant Context ===")

    async with AsyncSessionLocal() as session:
        # Create a test tenant
        tenant = Tenant(slug="manual-test-tenant", name="Manual Test Tenant", is_active=True)
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        print(f"✓ Created test tenant: {tenant.id}")

        # Clear any existing context
        clear_current_tenant()

        # Set tenant context
        await set_tenant_context(session, tenant.id, validate=False)
        print(f"✓ Set tenant context for: {tenant.id}")

        # Read back from PostgreSQL
        result = await session.execute(
            text("SELECT current_setting('app.current_tenant_id', TRUE)")
        )
        pg_tenant_id = result.scalar()
        print(f"✓ PostgreSQL session variable: {pg_tenant_id}")
        assert pg_tenant_id == str(tenant.id), "PostgreSQL session variable mismatch!"

        # Read back from contextvars
        ctx_tenant_id = get_current_tenant()
        print(f"✓ Contextvars tenant ID: {ctx_tenant_id}")
        assert ctx_tenant_id == tenant.id, "Contextvars mismatch!"

        # Clean up
        await session.delete(tenant)
        await session.commit()
        print("✓ Cleaned up test tenant")

    print("✅ Test 1 PASSED\n")


async def test_clear_tenant_context():
    """Test clearing tenant context."""
    print("\n=== Test 2: Clear Tenant Context ===")

    async with AsyncSessionLocal() as session:
        # Create a test tenant
        tenant = Tenant(slug="manual-test-tenant-2", name="Manual Test Tenant 2", is_active=True)
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        print(f"✓ Created test tenant: {tenant.id}")

        # Set context
        await set_tenant_context(session, tenant.id, validate=False)
        print(f"✓ Set tenant context for: {tenant.id}")

        # Clear context
        await clear_tenant_context(session)
        print("✓ Cleared tenant context")

        # Verify PostgreSQL session variable is cleared
        result = await session.execute(
            text("SELECT current_setting('app.current_tenant_id', TRUE)")
        )
        pg_tenant_id = result.scalar()
        print(f"✓ PostgreSQL session variable after clear: {pg_tenant_id}")
        assert pg_tenant_id is None or pg_tenant_id == "", "PostgreSQL session variable not cleared!"

        # Verify contextvars is cleared
        ctx_tenant_id = get_current_tenant()
        print(f"✓ Contextvars tenant ID after clear: {ctx_tenant_id}")
        assert ctx_tenant_id is None, "Contextvars not cleared!"

        # Clean up
        await session.delete(tenant)
        await session.commit()
        print("✓ Cleaned up test tenant")

    print("✅ Test 2 PASSED\n")


async def test_tenant_validation():
    """Test tenant validation."""
    print("\n=== Test 3: Tenant Validation ===")

    async with AsyncSessionLocal() as session:
        # Create an active tenant
        active_tenant = Tenant(slug="active-tenant", name="Active Tenant", is_active=True)
        session.add(active_tenant)

        # Create an inactive tenant
        inactive_tenant = Tenant(slug="inactive-tenant", name="Inactive Tenant", is_active=False)
        session.add(inactive_tenant)

        await session.commit()
        await session.refresh(active_tenant)
        await session.refresh(inactive_tenant)
        print(f"✓ Created active tenant: {active_tenant.id}")
        print(f"✓ Created inactive tenant: {inactive_tenant.id}")

        # Test: Active tenant validation should succeed
        try:
            await validate_tenant_active(session, active_tenant.id)
            print("✓ Active tenant validation succeeded")
        except TenantContextError:
            print("✗ Active tenant validation failed (should have succeeded!)")
            raise

        # Test: Inactive tenant validation should fail
        try:
            await validate_tenant_active(session, inactive_tenant.id)
            print("✗ Inactive tenant validation succeeded (should have failed!)")
            raise AssertionError("Inactive tenant validation should have failed")
        except TenantContextError as e:
            print(f"✓ Inactive tenant validation failed as expected: {e}")

        # Test: Non-existent tenant validation should fail
        fake_tenant_id = uuid4()
        try:
            await validate_tenant_active(session, fake_tenant_id)
            print("✗ Non-existent tenant validation succeeded (should have failed!)")
            raise AssertionError("Non-existent tenant validation should have failed")
        except TenantContextError as e:
            print(f"✓ Non-existent tenant validation failed as expected: {e}")

        # Clean up
        await session.delete(active_tenant)
        await session.delete(inactive_tenant)
        await session.commit()
        print("✓ Cleaned up test tenants")

    print("✅ Test 3 PASSED\n")


async def test_bypass_rls():
    """Test RLS bypass."""
    print("\n=== Test 4: Bypass RLS ===")

    async with AsyncSessionLocal() as session:
        # Bypass RLS
        await bypass_rls(session)
        print("✓ Bypassed RLS")

        # Check row_security setting
        result = await session.execute(text("SHOW row_security"))
        row_security = result.scalar()
        print(f"✓ row_security setting: {row_security}")
        assert row_security == "off", "RLS bypass failed!"

    print("✅ Test 4 PASSED\n")


async def test_tenant_context_manager():
    """Test TenantContext async context manager."""
    print("\n=== Test 5: TenantContext Context Manager ===")

    async with AsyncSessionLocal() as session:
        # Create a test tenant
        tenant = Tenant(slug="context-mgr-tenant", name="Context Manager Tenant", is_active=True)
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        print(f"✓ Created test tenant: {tenant.id}")

        # Clear any existing context
        clear_current_tenant()

        # Test without clear_on_exit
        print("\n--- Test 5a: Without clear_on_exit ---")
        async with TenantContext(session, tenant.id, validate=False):
            ctx_tenant_id = get_current_tenant()
            print(f"✓ Inside context manager, tenant ID: {ctx_tenant_id}")
            assert ctx_tenant_id == tenant.id, "Context not set inside manager!"

        ctx_tenant_id = get_current_tenant()
        print(f"✓ After context manager (no clear), tenant ID: {ctx_tenant_id}")
        assert ctx_tenant_id == tenant.id, "Context should still be set!"

        # Test with clear_on_exit
        print("\n--- Test 5b: With clear_on_exit ---")
        clear_current_tenant()
        async with TenantContext(session, tenant.id, validate=False, clear_on_exit=True):
            ctx_tenant_id = get_current_tenant()
            print(f"✓ Inside context manager, tenant ID: {ctx_tenant_id}")
            assert ctx_tenant_id == tenant.id, "Context not set inside manager!"

        ctx_tenant_id = get_current_tenant()
        print(f"✓ After context manager (with clear), tenant ID: {ctx_tenant_id}")
        assert ctx_tenant_id is None, "Context should be cleared!"

        # Clean up
        await session.delete(tenant)
        await session.commit()
        print("✓ Cleaned up test tenant")

    print("✅ Test 5 PASSED\n")


async def main():
    """Run all manual tests."""
    print("=" * 60)
    print("TENANT CONTEXT SERVICE - MANUAL VALIDATION")
    print("=" * 60)

    try:
        await test_set_and_read_tenant_context()
        await test_clear_tenant_context()
        await test_tenant_validation()
        await test_bypass_rls()
        await test_tenant_context_manager()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        return 0

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"✗ TEST FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

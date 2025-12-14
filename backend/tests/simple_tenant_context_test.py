"""
Simple tenant context validation script using existing seeded data.

Uses synchronous PostgreSQL connection for simplicity.
Tests against the seeded tenants from migration 319398410c85.

Run with: python tests/simple_tenant_context_test.py
"""

import psycopg2

# Test tenant IDs from seeded data
TENANT_ACME_ID = "11111111-1111-1111-1111-111111111111"
TENANT_GLOBEX_ID = "22222222-2222-2222-2222-222222222222"

# Database connection
DB_URL = "postgresql://knowledge_mapper_app_user:app_password_dev@localhost:5435/knowledge_mapper_db"


def test_set_and_read_tenant_context():
    """Test setting and reading tenant context."""
    print("\n=== Test 1: Set and Read Tenant Context ===")

    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()

    try:
        # Set tenant context for ACME
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, TRUE)",
            (TENANT_ACME_ID,)
        )
        print(f"✓ Set tenant context for ACME: {TENANT_ACME_ID}")

        # Read back the session variable
        cursor.execute("SELECT current_setting('app.current_tenant_id', TRUE)")
        result = cursor.fetchone()[0]
        print(f"✓ PostgreSQL session variable: {result}")

        assert result == TENANT_ACME_ID, "Session variable mismatch!"

        print("✅ Test 1 PASSED")

    finally:
        cursor.close()
        conn.close()


def test_clear_tenant_context():
    """Test clearing tenant context."""
    print("\n=== Test 2: Clear Tenant Context ===")

    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()

    try:
        # Set tenant context
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, TRUE)",
            (TENANT_ACME_ID,)
        )
        print(f"✓ Set tenant context for ACME: {TENANT_ACME_ID}")

        # Clear tenant context
        cursor.execute("SELECT set_config('app.current_tenant_id', NULL, TRUE)")
        print("✓ Cleared tenant context")

        # Verify it's cleared
        cursor.execute("SELECT current_setting('app.current_tenant_id', TRUE)")
        result = cursor.fetchone()[0]
        print(f"✓ PostgreSQL session variable after clear: {result}")

        assert result is None or result == "", "Session variable not cleared!"

        print("✅ Test 2 PASSED")

    finally:
        cursor.close()
        conn.close()


def test_rls_isolation():
    """Test that RLS isolates tenant data."""
    print("\n=== Test 3: RLS Tenant Isolation ===")

    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()

    try:
        # Set tenant context to ACME
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, TRUE)",
            (TENANT_ACME_ID,)
        )
        print(f"✓ Set tenant context for ACME: {TENANT_ACME_ID}")

        # Query users - should only see ACME users
        cursor.execute("SELECT COUNT(*) FROM users")
        acme_user_count = cursor.fetchone()[0]
        print(f"✓ ACME user count: {acme_user_count}")

        # Change tenant context to Globex
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, TRUE)",
            (TENANT_GLOBEX_ID,)
        )
        print(f"✓ Set tenant context for Globex: {TENANT_GLOBEX_ID}")

        # Query users - should only see Globex users
        cursor.execute("SELECT COUNT(*) FROM users")
        globex_user_count = cursor.fetchone()[0]
        print(f"✓ Globex user count: {globex_user_count}")

        # Verify counts are different (assuming seeded data has users for both)
        # ACME has 2 users, Globex has 2 users
        assert acme_user_count == 2, f"Expected 2 ACME users, got {acme_user_count}"
        assert globex_user_count == 2, f"Expected 2 Globex users, got {globex_user_count}"

        print("✅ Test 3 PASSED - Tenant isolation working!")

    finally:
        cursor.close()
        conn.close()


def test_no_context_returns_no_data():
    """Test that queries without tenant context return no data."""
    print("\n=== Test 4: No Context Returns No Data ===")

    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()

    try:
        # Clear any tenant context
        cursor.execute("SELECT set_config('app.current_tenant_id', NULL, TRUE)")
        print("✓ Cleared tenant context")

        # Query users - should return 0 rows
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"✓ User count without tenant context: {user_count}")

        assert user_count == 0, f"Expected 0 users, got {user_count}"

        print("✅ Test 4 PASSED - RLS blocks access without tenant context!")

    finally:
        cursor.close()
        conn.close()


def test_transaction_scoped_context():
    """Test that tenant context is transaction-scoped."""
    print("\n=== Test 5: Transaction-Scoped Context ===")

    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()

    try:
        # Set tenant context in first transaction
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, TRUE)",
            (TENANT_ACME_ID,)
        )
        print(f"✓ Set tenant context for ACME: {TENANT_ACME_ID}")

        # Commit transaction
        conn.commit()
        print("✓ Committed transaction")

        # Start new transaction and check if context is cleared
        cursor.execute("SELECT current_setting('app.current_tenant_id', TRUE)")
        result = cursor.fetchone()[0]
        print(f"✓ PostgreSQL session variable after commit: {result}")

        # Should be cleared (transaction-scoped)
        assert result is None or result == "", "Session variable should be cleared after transaction!"

        print("✅ Test 5 PASSED - Context is transaction-scoped!")

    finally:
        cursor.close()
        conn.close()


def main():
    """Run all tests."""
    print("=" * 60)
    print("TENANT CONTEXT SERVICE - SIMPLE VALIDATION")
    print("=" * 60)

    try:
        test_set_and_read_tenant_context()
        test_clear_tenant_context()
        test_rls_isolation()
        test_no_context_returns_no_data()
        test_transaction_scoped_context()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nCore tenant context functionality is working correctly:")
        print("  1. Setting tenant context works")
        print("  2. Clearing tenant context works")
        print("  3. RLS isolates tenant data correctly")
        print("  4. Queries without context return no data (secure default)")
        print("  5. Context is transaction-scoped (SET LOCAL)")
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
    import sys
    sys.exit(main())

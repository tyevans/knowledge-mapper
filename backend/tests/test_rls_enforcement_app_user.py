"""
Test Row-Level Security (RLS) enforcement with knowledge_mapper_app_user.

This test verifies that:
1. knowledge_mapper_app_user (NO BYPASSRLS) respects RLS policies
2. Tenant isolation works correctly with application user
3. Cross-tenant access is properly blocked by RLS policies
4. RLS policies correctly enforce tenant_id filtering

SECURITY CRITICAL:
==================
These tests validate that the application user cannot bypass RLS policies
and that tenant data isolation is properly enforced at the database level.

This is the primary defense against cross-tenant data leakage.

Test Data:
==========
Uses seeded development data from migration 319398410c85:

Tenant: ACME Corporation (acme-corp)
  ID: 11111111-1111-1111-1111-111111111111
  Users:
    - alice@acme-corp.example (cbd0900c-44b3-4e75-b093-0b6c2282183f)
    - bob@acme-corp.example (59be274d-c55a-4945-a420-8c49ced43d86)

Tenant: Globex Inc (globex-inc)
  ID: 22222222-2222-2222-2222-222222222222
  Users:
    - charlie@globex-inc.example (50b5edc2-6740-47f3-9d0f-eafbb7c1652a)
    - diana@globex-inc.example (7c53def1-64b4-4190-964d-a0e0ac258f85)
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Test tenant IDs
TENANT_ACME_ID = "11111111-1111-1111-1111-111111111111"
TENANT_GLOBEX_ID = "22222222-2222-2222-2222-222222222222"

# Application user URL (NO BYPASSRLS - RLS policies enforced)
# Uses synchronous driver for testing (asyncpg doesn't support SET LOCAL in transactions easily)
APP_USER_URL = "postgresql://knowledge_mapper_app_user:app_password_dev@localhost:5435/knowledge_mapper_db"


@pytest.fixture(scope="module")
def app_user_engine():
    """Create database engine with knowledge_mapper_app_user (NO BYPASSRLS)."""
    engine = create_engine(
        APP_USER_URL,
        poolclass=NullPool,  # No connection pooling for tests
        echo=False,  # Set to True for SQL debugging
    )
    yield engine
    engine.dispose()


@pytest.fixture
def app_user_session(app_user_engine):
    """Create database session with knowledge_mapper_app_user."""
    Session = sessionmaker(bind=app_user_engine)
    session = Session()
    yield session
    session.close()


class TestRLSEnforcementWithAppUser:
    """Test RLS enforcement with knowledge_mapper_app_user (NO BYPASSRLS)."""

    def test_app_user_cannot_bypass_rls(self, app_user_session):
        """
        Test that knowledge_mapper_app_user does NOT have BYPASSRLS privilege.

        This verifies the core security fix: the application user should not
        be able to bypass RLS policies.
        """
        result = app_user_session.execute(
            text("""
                SELECT rolbypassrls
                FROM pg_roles
                WHERE rolname = 'knowledge_mapper_app_user'
            """)
        ).fetchone()

        assert result is not None, "knowledge_mapper_app_user role not found"
        assert result[0] is False, "CRITICAL: knowledge_mapper_app_user has BYPASSRLS privilege!"

    def test_rls_blocks_access_without_tenant_context(self, app_user_session):
        """
        Test that RLS blocks all access when tenant context is not set.

        Without setting app.current_tenant_id, all queries should return 0 rows.
        This is the fail-safe behavior.
        """
        # Try to query users without setting tenant context
        result = app_user_session.execute(text("SELECT COUNT(*) FROM users")).fetchone()

        # Should return 0 rows (RLS blocks access without tenant context)
        assert result[0] == 0, "RLS should block access without tenant context"

    def test_rls_allows_access_to_own_tenant_data(self, app_user_session):
        """
        Test that RLS allows access to data for the current tenant.

        When app.current_tenant_id is set, queries should return only data
        for that tenant.
        """
        # Set tenant context to ACME Corporation
        app_user_session.execute(
            text(f"SET LOCAL app.current_tenant_id = '{TENANT_ACME_ID}'")
        )

        # Query users - should see only ACME users
        result = app_user_session.execute(
            text("SELECT email FROM users ORDER BY email")
        ).fetchall()

        emails = [row[0] for row in result]

        # Should see ACME users
        assert "alice@acme-corp.example" in emails
        assert "bob@acme-corp.example" in emails

        # Should NOT see Globex users (blocked by RLS)
        assert "charlie@globex-inc.example" not in emails
        assert "diana@globex-inc.example" not in emails

        # Verify we got exactly 2 ACME users
        assert len(emails) == 2

    def test_rls_blocks_cross_tenant_access(self, app_user_session):
        """
        Test that RLS blocks access to other tenants' data.

        Even if we explicitly query for another tenant's user, RLS should
        block the query and return 0 rows.
        """
        # Set tenant context to ACME Corporation
        app_user_session.execute(
            text(f"SET LOCAL app.current_tenant_id = '{TENANT_ACME_ID}'")
        )

        # Try to directly query a Globex user by email
        result = app_user_session.execute(
            text("SELECT email FROM users WHERE email = 'charlie@globex-inc.example'")
        ).fetchall()

        # RLS should block this - no results returned
        assert len(result) == 0, "RLS should block cross-tenant access"

    def test_rls_enforces_tenant_context_switch(self, app_user_session):
        """
        Test that RLS correctly filters when tenant context is switched.

        When we change app.current_tenant_id, the visible data should change.
        """
        # Set tenant context to ACME Corporation
        app_user_session.execute(
            text(f"SET LOCAL app.current_tenant_id = '{TENANT_ACME_ID}'")
        )
        app_user_session.commit()

        # New transaction - set tenant context to Globex Inc
        app_user_session.execute(
            text(f"SET LOCAL app.current_tenant_id = '{TENANT_GLOBEX_ID}'")
        )

        # Query users - should now see only Globex users
        result = app_user_session.execute(
            text("SELECT email FROM users ORDER BY email")
        ).fetchall()

        emails = [row[0] for row in result]

        # Should see Globex users
        assert "charlie@globex-inc.example" in emails
        assert "diana@globex-inc.example" in emails

        # Should NOT see ACME users (blocked by RLS)
        assert "alice@acme-corp.example" not in emails
        assert "bob@acme-corp.example" not in emails

        # Verify we got exactly 2 Globex users
        assert len(emails) == 2

    def test_rls_enforces_oauth_providers_isolation(self, app_user_session):
        """
        Test that RLS enforces tenant isolation for oauth_providers table.

        Each tenant should only see their own OAuth provider configuration.
        """
        # Set tenant context to ACME Corporation
        app_user_session.execute(
            text(f"SET LOCAL app.current_tenant_id = '{TENANT_ACME_ID}'")
        )

        # Query OAuth providers
        result = app_user_session.execute(
            text("SELECT tenant_id FROM oauth_providers")
        ).fetchall()

        tenant_ids = [str(row[0]) for row in result]

        # Should see only ACME's provider
        assert TENANT_ACME_ID in tenant_ids
        assert TENANT_GLOBEX_ID not in tenant_ids
        assert len(tenant_ids) == 1

    def test_rls_blocks_insert_to_wrong_tenant(self, app_user_session):
        """
        Test that RLS blocks INSERT operations to wrong tenant.

        When tenant context is set to ACME, trying to insert a user for Globex
        should fail due to RLS WITH CHECK policy.
        """
        import uuid

        # Set tenant context to ACME Corporation
        app_user_session.execute(
            text(f"SET LOCAL app.current_tenant_id = '{TENANT_ACME_ID}'")
        )

        # Try to insert a user for Globex (should fail RLS WITH CHECK)
        user_id = str(uuid.uuid4())
        try:
            app_user_session.execute(
                text("""
                    INSERT INTO users (id, tenant_id, oauth_subject, email, display_name, is_active)
                    VALUES (
                        CAST(:user_id AS uuid),
                        CAST(:tenant_id AS uuid),
                        :oauth_subject,
                        :email,
                        :display_name,
                        true
                    )
                """),
                {
                    "user_id": user_id,
                    "tenant_id": TENANT_GLOBEX_ID,  # Wrong tenant!
                    "oauth_subject": user_id,
                    "email": "test@globex-inc.example",
                    "display_name": "Test User",
                },
            )
            app_user_session.commit()

            # If we get here, RLS failed to block the insert
            pytest.fail("RLS should have blocked cross-tenant INSERT")

        except Exception as e:
            # Expected: RLS should block this insert
            app_user_session.rollback()
            assert "new row violates row-level security policy" in str(e).lower()

    def test_rls_allows_insert_to_correct_tenant(self, app_user_session):
        """
        Test that RLS allows INSERT operations to the correct tenant.

        When tenant context matches the tenant_id in the INSERT, it should succeed.
        """
        import uuid

        # Set tenant context to ACME Corporation
        app_user_session.execute(
            text(f"SET LOCAL app.current_tenant_id = '{TENANT_ACME_ID}'")
        )

        # Insert a user for ACME (should succeed)
        user_id = str(uuid.uuid4())
        try:
            app_user_session.execute(
                text("""
                    INSERT INTO users (id, tenant_id, oauth_subject, email, display_name, is_active)
                    VALUES (
                        CAST(:user_id AS uuid),
                        CAST(:tenant_id AS uuid),
                        :oauth_subject,
                        :email,
                        :display_name,
                        true
                    )
                """),
                {
                    "user_id": user_id,
                    "tenant_id": TENANT_ACME_ID,  # Correct tenant
                    "oauth_subject": user_id,
                    "email": f"test-{user_id[:8]}@acme-corp.example",
                    "display_name": "Test User",
                },
            )
            app_user_session.commit()

            # Set tenant context again (commit started a new transaction)
            app_user_session.execute(
                text(f"SET LOCAL app.current_tenant_id = '{TENANT_ACME_ID}'")
            )

            # Verify the user was inserted
            result = app_user_session.execute(
                text("SELECT email FROM users WHERE id = CAST(:user_id AS uuid)"),
                {"user_id": user_id},
            ).fetchone()

            assert result is not None
            assert result[0] == f"test-{user_id[:8]}@acme-corp.example"

            # Clean up test data
            app_user_session.execute(
                text("DELETE FROM users WHERE id = CAST(:user_id AS uuid)"),
                {"user_id": user_id},
            )
            app_user_session.commit()

        except Exception:
            # If something went wrong, rollback
            app_user_session.rollback()
            raise

    def test_migration_user_has_bypassrls(self):
        """
        Test that knowledge_mapper_migration_user DOES have BYPASSRLS privilege.

        This verifies that migrations can still run with administrative privileges.
        """
        migration_user_url = "postgresql://knowledge_mapper_migration_user:migration_password_dev@localhost:5435/knowledge_mapper_db"
        engine = create_engine(migration_user_url, poolclass=NullPool)
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            result = session.execute(
                text("""
                    SELECT rolbypassrls
                    FROM pg_roles
                    WHERE rolname = 'knowledge_mapper_migration_user'
                """)
            ).fetchone()

            assert result is not None, "knowledge_mapper_migration_user role not found"
            assert result[0] is True, "knowledge_mapper_migration_user should have BYPASSRLS privilege"

        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])

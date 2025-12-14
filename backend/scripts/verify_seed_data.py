#!/usr/bin/env python3
"""
Verify development seed data from TASK-005 migration.

This script validates that the seed migration created the expected test data:
- 2 tenants (acme-corp, globex-inc)
- 4 users with UUIDs matching TASK-007 Keycloak realm
- 2 OAuth provider configurations

Run this script after running migrations to verify seed data integrity.
"""

import asyncio
import sys
from sqlalchemy import text
from app.core.database import engine

# Expected tenant UUIDs
TENANT_ACME_ID = '11111111-1111-1111-1111-111111111111'
TENANT_GLOBEX_ID = '22222222-2222-2222-2222-222222222222'

# Expected user UUIDs (MUST match TASK-007 Keycloak realm)
EXPECTED_USERS = {
    'alice@acme-corp.example': {
        'id': 'cbd0900c-44b3-4e75-b093-0b6c2282183f',
        'tenant_id': TENANT_ACME_ID,
        'display_name': 'Alice (ACME Admin)',
    },
    'bob@acme-corp.example': {
        'id': '59be274d-c55a-4945-a420-8c49ced43d86',
        'tenant_id': TENANT_ACME_ID,
        'display_name': 'Bob (ACME User)',
    },
    'charlie@globex-inc.example': {
        'id': '50b5edc2-6740-47f3-9d0f-eafbb7c1652a',
        'tenant_id': TENANT_GLOBEX_ID,
        'display_name': 'Charlie (Globex Admin)',
    },
    'diana@globex-inc.example': {
        'id': '7c53def1-64b4-4190-964d-a0e0ac258f85',
        'tenant_id': TENANT_GLOBEX_ID,
        'display_name': 'Diana (Globex User)',
    },
}


async def verify_tenants() -> bool:
    """Verify that expected tenants exist."""
    print("\n=== Verifying Tenants ===")
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, slug, name FROM tenants WHERE id IN (:acme, :globex)"),
            {'acme': TENANT_ACME_ID, 'globex': TENANT_GLOBEX_ID}
        )
        tenants = {str(t.id): t for t in result.fetchall()}

        if TENANT_ACME_ID not in tenants:
            print("✗ ACME Corp tenant NOT FOUND")
            return False

        if TENANT_GLOBEX_ID not in tenants:
            print("✗ Globex Inc tenant NOT FOUND")
            return False

        acme = tenants[TENANT_ACME_ID]
        globex = tenants[TENANT_GLOBEX_ID]

        print(f"✓ ACME Corp: {acme.slug} - {acme.name}")
        print(f"✓ Globex Inc: {globex.slug} - {globex.name}")

        return True


async def verify_oauth_providers() -> bool:
    """Verify that OAuth providers are configured for each tenant."""
    print("\n=== Verifying OAuth Providers ===")
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT tenant_id, provider_type, issuer, client_id
                FROM oauth_providers
                WHERE tenant_id IN (:acme, :globex)
            """),
            {'acme': TENANT_ACME_ID, 'globex': TENANT_GLOBEX_ID}
        )
        providers = {str(p.tenant_id): p for p in result.fetchall()}

        if TENANT_ACME_ID not in providers:
            print("✗ ACME Corp OAuth provider NOT FOUND")
            return False

        if TENANT_GLOBEX_ID not in providers:
            print("✗ Globex Inc OAuth provider NOT FOUND")
            return False

        acme = providers[TENANT_ACME_ID]
        globex = providers[TENANT_GLOBEX_ID]

        print(f"✓ ACME Corp: {acme.provider_type} - {acme.issuer}")
        print(f"  Client ID: {acme.client_id}")
        print(f"✓ Globex Inc: {globex.provider_type} - {globex.issuer}")
        print(f"  Client ID: {globex.client_id}")

        return True


async def verify_users() -> bool:
    """Verify that all expected users exist with correct UUIDs."""
    print("\n=== Verifying Users ===")
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT id, email, tenant_id, oauth_subject, display_name
                FROM users
                WHERE email IN (:alice, :bob, :charlie, :diana)
            """),
            {
                'alice': 'alice@acme-corp.example',
                'bob': 'bob@acme-corp.example',
                'charlie': 'charlie@globex-inc.example',
                'diana': 'diana@globex-inc.example',
            }
        )
        users = {u.email: u for u in result.fetchall()}

        all_valid = True
        for email, expected in EXPECTED_USERS.items():
            if email not in users:
                print(f"✗ {email} NOT FOUND")
                all_valid = False
                continue

            user = users[email]
            uuid_match = str(user.id) == expected['id']
            subject_match = user.oauth_subject == expected['id']
            tenant_match = str(user.tenant_id) == expected['tenant_id']
            name_match = user.display_name == expected['display_name']

            if uuid_match and subject_match and tenant_match and name_match:
                print(f"✓ {email}: {user.display_name}")
                print(f"  UUID: {user.id}")
                print(f"  OAuth Subject: {user.oauth_subject}")
            else:
                print(f"✗ {email}: MISMATCH")
                if not uuid_match:
                    print(f"  UUID mismatch: expected {expected['id']}, got {user.id}")
                if not subject_match:
                    print(f"  Subject mismatch: expected {expected['id']}, got {user.oauth_subject}")
                if not tenant_match:
                    print(f"  Tenant mismatch: expected {expected['tenant_id']}, got {user.tenant_id}")
                if not name_match:
                    print(f"  Name mismatch: expected {expected['display_name']}, got {user.display_name}")
                all_valid = False

        return all_valid


async def verify_uuid_coordination() -> bool:
    """
    Verify UUID coordination with TASK-007 Keycloak realm.

    This is the most critical validation - the user UUIDs in the database
    MUST match the UUIDs in the Keycloak realm from TASK-007, otherwise
    OAuth authentication will fail.
    """
    print("\n=== Verifying UUID Coordination (TASK-005 <-> TASK-007) ===")
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, email, oauth_subject FROM users ORDER BY email")
        )
        users = result.fetchall()

        all_match = True
        for user in users:
            if user.email in EXPECTED_USERS:
                expected_uuid = EXPECTED_USERS[user.email]['id']
                actual_uuid = str(user.id)
                actual_subject = user.oauth_subject

                if actual_uuid == expected_uuid and actual_subject == expected_uuid:
                    print(f"✓ {user.email}: UUID coordination OK")
                else:
                    print(f"✗ {user.email}: UUID coordination FAILED")
                    print(f"  Expected: {expected_uuid}")
                    print(f"  Got UUID: {actual_uuid}")
                    print(f"  Got Subject: {actual_subject}")
                    all_match = False

        return all_match


async def main():
    """Run all verification checks."""
    print("=" * 70)
    print("TASK-005 Seed Data Verification")
    print("=" * 70)

    try:
        tenants_ok = await verify_tenants()
        providers_ok = await verify_oauth_providers()
        users_ok = await verify_users()
        coordination_ok = await verify_uuid_coordination()

        print("\n" + "=" * 70)
        print("Verification Summary")
        print("=" * 70)
        print(f"Tenants:           {'✓ PASS' if tenants_ok else '✗ FAIL'}")
        print(f"OAuth Providers:   {'✓ PASS' if providers_ok else '✗ FAIL'}")
        print(f"Users:             {'✓ PASS' if users_ok else '✗ FAIL'}")
        print(f"UUID Coordination: {'✓ PASS' if coordination_ok else '✗ FAIL'}")
        print("=" * 70)

        if all([tenants_ok, providers_ok, users_ok, coordination_ok]):
            print("\n✓ All verification checks PASSED!")
            print("  Seed data is correctly configured and matches TASK-007 Keycloak realm.")
            return 0
        else:
            print("\n✗ Some verification checks FAILED!")
            print("  Please review the errors above and check the seed migration.")
            return 1

    except Exception as e:
        print(f"\n✗ Verification failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))

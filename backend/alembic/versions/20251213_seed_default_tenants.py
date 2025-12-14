"""Seed default tenants for development and testing

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2025-12-13 22:30:00.000000

Seeds tenants that match the Keycloak setup script (keycloak/setup-realm.sh):
- Platform tenant (00000000-...) for platform admin
- acme-corp tenant (11111111-...) for Alice, Bob
- demo-org tenant (22222222-...) for Charlie, Diana
- test-tenant (33333333-...) for Playwright test users

These must exist before users with these tenant_ids can create data.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6g7h8i9j0"
down_revision: Union[str, None] = "d4e5f6g7h8i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Insert default tenants matching Keycloak setup.
    Uses ON CONFLICT to be idempotent.
    """
    op.execute("""
        INSERT INTO tenants (id, slug, name, settings, is_active, created_at, updated_at)
        VALUES
            (
                '00000000-0000-0000-0000-000000000000',
                'platform',
                'Platform',
                '{"description": "Platform administration tenant"}',
                true,
                NOW(),
                NOW()
            ),
            (
                '11111111-1111-1111-1111-111111111111',
                'acme-corp',
                'Acme Corporation',
                '{"description": "Demo tenant for acme-corp"}',
                true,
                NOW(),
                NOW()
            ),
            (
                '22222222-2222-2222-2222-222222222222',
                'demo-org',
                'Demo Organization',
                '{"description": "Demo tenant for demo-org"}',
                true,
                NOW(),
                NOW()
            ),
            (
                '33333333-3333-3333-3333-333333333333',
                'test-tenant',
                'Test Tenant',
                '{"description": "Default tenant for Playwright and API tests"}',
                true,
                NOW(),
                NOW()
            )
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    """
    Remove seeded tenants.
    Note: This will fail if there are foreign key references to these tenants.
    """
    op.execute("""
        DELETE FROM tenants
        WHERE id IN (
            '00000000-0000-0000-0000-000000000000',
            '11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222',
            '33333333-3333-3333-3333-333333333333'
        );
    """)

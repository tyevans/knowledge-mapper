"""Add user_tenant_memberships table for multi-tenant user support

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2025-12-13 12:00:00.000000

Creates the user_tenant_memberships table to support users belonging to
multiple tenants. This enables a single user to have different roles in
different tenants.

Migration steps:
1. Create user_tenant_memberships table with RLS
2. Migrate existing user.tenant_id data to memberships
3. Make users.tenant_id nullable (backward compatibility)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "b2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create user_tenant_memberships table and migrate existing data.
    """
    # Create the membership_role enum type using raw SQL
    # (asyncpg has issues with ENUM.create() checkfirst=True)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'membership_role') THEN
                CREATE TYPE membership_role AS ENUM ('owner', 'admin', 'member');
            END IF;
        END
        $$;
    """)

    # Reference the enum for use in table creation
    membership_role_enum = postgresql.ENUM(
        'owner', 'admin', 'member',
        name='membership_role',
        create_type=False  # Don't create, we already did above
    )

    # Create user_tenant_memberships table
    op.create_table(
        'user_tenant_memberships',
        sa.Column(
            'id',
            sa.UUID(),
            nullable=False,
            comment='UUID primary key for security and distributed ID generation'
        ),
        sa.Column(
            'user_id',
            sa.UUID(),
            nullable=False,
            comment='User who has membership in the tenant'
        ),
        sa.Column(
            'tenant_id',
            sa.UUID(),
            nullable=False,
            comment='Tenant the user has membership in'
        ),
        sa.Column(
            'role',
            membership_role_enum,
            nullable=False,
            server_default='member',
            comment="User's role within this tenant"
        ),
        sa.Column(
            'is_default',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment="Whether this is the user's default tenant"
        ),
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default='true',
            comment='Soft delete flag (False = membership revoked but preserved)'
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()')
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id'],
            ['tenants.id'],
            ondelete='CASCADE'
        ),
        sa.UniqueConstraint(
            'user_id',
            'tenant_id',
            name='uq_user_tenant_membership'
        )
    )

    # Create indexes
    op.create_index(
        op.f('ix_user_tenant_memberships_id'),
        'user_tenant_memberships',
        ['id'],
        unique=False
    )
    op.create_index(
        op.f('ix_user_tenant_memberships_user_id'),
        'user_tenant_memberships',
        ['user_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_user_tenant_memberships_tenant_id'),
        'user_tenant_memberships',
        ['tenant_id'],
        unique=False
    )
    op.create_index(
        'ix_user_tenant_memberships_user_tenant',
        'user_tenant_memberships',
        ['user_id', 'tenant_id'],
        unique=False
    )

    # Enable Row-Level Security (RLS)
    op.execute("ALTER TABLE user_tenant_memberships ENABLE ROW LEVEL SECURITY")

    # Create RLS policy for tenant isolation
    # Users can only see memberships in their current tenant context
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON user_tenant_memberships
        USING (tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
            '00000000-0000-0000-0000-000000000000'::UUID
        ))
    """)

    # Create policy for users to see their own memberships across tenants
    # This is needed for the tenant selection flow
    op.execute("""
        CREATE POLICY user_own_memberships_policy ON user_tenant_memberships
        FOR SELECT
        USING (
            user_id IN (
                SELECT id FROM users
                WHERE oauth_subject = current_setting('app.current_user_subject', TRUE)
            )
        )
    """)

    # Migrate existing data: create membership records from users.tenant_id
    op.execute("""
        INSERT INTO user_tenant_memberships (id, user_id, tenant_id, role, is_default, is_active, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            id,
            tenant_id,
            'member',
            true,
            is_active,
            created_at,
            NOW()
        FROM users
        WHERE tenant_id IS NOT NULL
    """)

    # Make users.tenant_id nullable for backward compatibility
    # We keep the column for now to support gradual migration
    op.alter_column(
        'users',
        'tenant_id',
        existing_type=sa.UUID(),
        nullable=True
    )


def downgrade() -> None:
    """
    Reverse the migration: drop user_tenant_memberships and restore users.tenant_id.
    """
    # Make users.tenant_id required again
    # First, ensure all users have a tenant_id from their memberships
    op.execute("""
        UPDATE users u
        SET tenant_id = (
            SELECT tenant_id
            FROM user_tenant_memberships m
            WHERE m.user_id = u.id AND m.is_default = true
            LIMIT 1
        )
        WHERE u.tenant_id IS NULL
    """)

    # If still null, pick any membership
    op.execute("""
        UPDATE users u
        SET tenant_id = (
            SELECT tenant_id
            FROM user_tenant_memberships m
            WHERE m.user_id = u.id
            LIMIT 1
        )
        WHERE u.tenant_id IS NULL
    """)

    op.alter_column(
        'users',
        'tenant_id',
        existing_type=sa.UUID(),
        nullable=False
    )

    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS user_own_memberships_policy ON user_tenant_memberships")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON user_tenant_memberships")

    # Disable RLS
    op.execute("ALTER TABLE user_tenant_memberships DISABLE ROW LEVEL SECURITY")

    # Drop indexes
    op.drop_index('ix_user_tenant_memberships_user_tenant', table_name='user_tenant_memberships')
    op.drop_index(op.f('ix_user_tenant_memberships_tenant_id'), table_name='user_tenant_memberships')
    op.drop_index(op.f('ix_user_tenant_memberships_user_id'), table_name='user_tenant_memberships')
    op.drop_index(op.f('ix_user_tenant_memberships_id'), table_name='user_tenant_memberships')

    # Drop table
    op.drop_table('user_tenant_memberships')

    # Drop enum type using raw SQL (asyncpg compatibility)
    op.execute("DROP TYPE IF EXISTS membership_role")

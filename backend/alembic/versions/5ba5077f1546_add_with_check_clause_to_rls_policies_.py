"""Add WITH CHECK clause to RLS policies for INSERT/UPDATE operations

Revision ID: 5ba5077f1546
Revises: e10757622a70
Create Date: 2025-11-16 20:29:15.185093

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ba5077f1546'
down_revision: Union[str, None] = 'e10757622a70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade database schema.

    This function applies the forward migration, creating or modifying
    database objects to move the schema to the new version.
    """
    # Drop existing RLS policies (they only have USING clause, no WITH CHECK)
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON users")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON oauth_providers")

    # Recreate RLS policies with both USING (for SELECT) and WITH CHECK (for INSERT/UPDATE)
    # USING: Controls which rows are visible for SELECT, UPDATE, DELETE
    # WITH CHECK: Controls which rows can be inserted or updated

    # Users table policy
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON users
        USING (tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
            '00000000-0000-0000-0000-000000000000'::UUID
        ))
        WITH CHECK (tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
            '00000000-0000-0000-0000-000000000000'::UUID
        ))
    """)

    # OAuth providers table policy
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON oauth_providers
        USING (tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
            '00000000-0000-0000-0000-000000000000'::UUID
        ))
        WITH CHECK (tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
            '00000000-0000-0000-0000-000000000000'::UUID
        ))
    """)


def downgrade() -> None:
    """
    Downgrade database schema.

    This function applies the reverse migration, undoing the changes
    made in upgrade() to return the schema to the previous version.

    Important: Downgrades should be tested to ensure data safety.
    """
    # Drop policies with WITH CHECK clause
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON users")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON oauth_providers")

    # Recreate policies with only USING clause (original version)
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON users
        USING (tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
            '00000000-0000-0000-0000-000000000000'::UUID
        ))
    """)

    op.execute("""
        CREATE POLICY tenant_isolation_policy ON oauth_providers
        USING (tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
            '00000000-0000-0000-0000-000000000000'::UUID
        ))
    """)

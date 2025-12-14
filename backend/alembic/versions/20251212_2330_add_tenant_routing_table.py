"""Add tenant routing table for event store mapping

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2025-12-12 23:30:00.000000

Creates the tenant_routing table for managing tenant-to-event-store mappings.
This table is used by eventsource-py's TenantStoreRouter for routing
event operations to the correct store during migrations.

Note: This is an infrastructure table and does NOT have RLS enabled.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6g7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create tenant_routing table for event store mapping.
    """
    # Create enum type for migration state using raw SQL (asyncpg compatibility)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tenant_migration_state') THEN
                CREATE TYPE tenant_migration_state AS ENUM ('NORMAL', 'BULK_COPY', 'DUAL_WRITE', 'CUTOVER_PAUSED', 'MIGRATED');
            END IF;
        END
        $$;
    """)

    # Reference the enum for use in table creation (don't create, we already did above)
    migration_state_enum = postgresql.ENUM(
        "NORMAL",
        "BULK_COPY",
        "DUAL_WRITE",
        "CUTOVER_PAUSED",
        "MIGRATED",
        name="tenant_migration_state",
        create_type=False,
    )

    # Create tenant_routing table
    op.create_table(
        "tenant_routing",
        # Primary key
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
            comment="Tenant UUID (references tenants.id)",
        ),
        # Store configuration
        sa.Column(
            "store_id",
            sa.String(length=255),
            nullable=False,
            default="default",
            comment="Event store identifier this tenant routes to",
        ),
        # Migration state
        sa.Column(
            "migration_state",
            migration_state_enum,
            nullable=False,
            server_default="NORMAL",
            comment="Current migration state for routing decisions",
        ),
        sa.Column(
            "active_migration_id",
            sa.UUID(),
            nullable=True,
            comment="Active migration ID if currently migrating",
        ),
        sa.Column(
            "target_store_id",
            sa.String(length=255),
            nullable=True,
            comment="Target store ID during migration",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="When this routing was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="When this routing was last updated",
        ),
        # Constraints
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_routing_tenant_id",
            ondelete="CASCADE",
        ),
    )

    # Indexes for common queries
    op.create_index(
        "ix_tenant_routing_store_id",
        "tenant_routing",
        ["store_id"],
    )
    op.create_index(
        "ix_tenant_routing_migration_state",
        "tenant_routing",
        ["migration_state"],
    )
    op.create_index(
        "ix_tenant_routing_active_migration",
        "tenant_routing",
        ["active_migration_id"],
        postgresql_where=sa.text("active_migration_id IS NOT NULL"),
    )

    # ==========================================================================
    # Migrations Table - Track live migrations
    # ==========================================================================
    # Create enum type for migration phase using raw SQL (asyncpg compatibility)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'migration_phase') THEN
                CREATE TYPE migration_phase AS ENUM ('PENDING', 'BULK_COPY', 'DUAL_WRITE', 'CUTOVER', 'COMPLETED', 'ABORTED', 'FAILED');
            END IF;
        END
        $$;
    """)

    # Reference the enum for use in table creation (don't create, we already did above)
    migration_phase_enum = postgresql.ENUM(
        "PENDING",
        "BULK_COPY",
        "DUAL_WRITE",
        "CUTOVER",
        "COMPLETED",
        "ABORTED",
        "FAILED",
        name="migration_phase",
        create_type=False,
    )

    op.create_table(
        "migrations",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            comment="Unique migration identifier",
        ),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
            comment="Tenant being migrated",
        ),
        sa.Column(
            "source_store_id",
            sa.String(length=255),
            nullable=False,
            comment="Source event store ID",
        ),
        sa.Column(
            "target_store_id",
            sa.String(length=255),
            nullable=False,
            comment="Target event store ID",
        ),
        sa.Column(
            "phase",
            migration_phase_enum,
            nullable=False,
            server_default="PENDING",
            comment="Current migration phase",
        ),
        sa.Column(
            "events_total",
            sa.BigInteger(),
            nullable=False,
            default=0,
            comment="Total events to migrate",
        ),
        sa.Column(
            "events_copied",
            sa.BigInteger(),
            nullable=False,
            default=0,
            comment="Events copied so far",
        ),
        sa.Column(
            "last_source_position",
            sa.BigInteger(),
            nullable=True,
            comment="Last processed source position",
        ),
        sa.Column(
            "last_target_position",
            sa.BigInteger(),
            nullable=True,
            comment="Last target position written",
        ),
        sa.Column(
            "is_paused",
            sa.Boolean(),
            nullable=False,
            default=False,
            comment="Whether migration is paused",
        ),
        sa.Column(
            "pause_reason",
            sa.Text(),
            nullable=True,
            comment="Reason for pause",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last error message",
        ),
        sa.Column(
            "config",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
            comment="Migration configuration",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "bulk_copy_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "bulk_copy_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "dual_write_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "cutover_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_by",
            sa.String(length=255),
            nullable=True,
            comment="User who initiated migration",
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_migrations_tenant_id",
            ondelete="CASCADE",
        ),
    )

    op.create_index("ix_migrations_tenant_id", "migrations", ["tenant_id"])
    op.create_index("ix_migrations_phase", "migrations", ["phase"])
    op.create_index(
        "ix_migrations_active",
        "migrations",
        ["tenant_id", "phase"],
        postgresql_where=sa.text(
            "phase NOT IN ('COMPLETED', 'ABORTED', 'FAILED')"
        ),
    )


def downgrade() -> None:
    """
    Drop tenant routing and migrations tables.
    """
    op.drop_table("migrations")
    op.drop_table("tenant_routing")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS migration_phase")
    op.execute("DROP TYPE IF EXISTS tenant_migration_state")

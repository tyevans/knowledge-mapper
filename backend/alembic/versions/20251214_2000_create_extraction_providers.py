"""Create extraction_providers table with RLS.

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2025-12-14 20:00:00.000000

This migration creates:
- extraction_providers: Tenant-scoped extraction provider configurations
- RLS policies for multi-tenant isolation
- Support for Ollama, OpenAI, and Anthropic providers
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON, ENUM


# revision identifiers, used by Alembic.
revision: str = "s9t0u1v2w3x4"
down_revision: Union[str, None] = "r8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create extraction_providers table and RLS policies."""

    # ==========================================================================
    # Create Enum Type (IF NOT EXISTS for idempotency)
    # ==========================================================================

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'extraction_provider_type') THEN
                CREATE TYPE extraction_provider_type AS ENUM (
                    'ollama',
                    'openai',
                    'anthropic'
                );
            END IF;
        END$$;
    """
    )

    # ==========================================================================
    # Create extraction_providers Table
    # ==========================================================================

    op.create_table(
        "extraction_providers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "provider_type",
            ENUM(
                "ollama",
                "openai",
                "anthropic",
                name="extraction_provider_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "config",
            JSON(),
            nullable=False,
            server_default="{}",
            comment="Provider-specific configuration (may contain encrypted fields)",
        ),
        # Model settings
        sa.Column(
            "default_model",
            sa.String(255),
            nullable=True,
            comment="Default model for extraction (e.g., gpt-4o, gemma3:12b)",
        ),
        sa.Column(
            "embedding_model",
            sa.String(255),
            nullable=True,
            comment="Model for embeddings (e.g., text-embedding-3-small)",
        ),
        # Operational settings
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this is the default provider for the tenant",
        ),
        sa.Column(
            "rate_limit_rpm",
            sa.Integer(),
            nullable=False,
            server_default="30",
            comment="Requests per minute limit",
        ),
        sa.Column(
            "max_context_length",
            sa.Integer(),
            nullable=False,
            server_default="4000",
            comment="Maximum context length for extraction",
        ),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
            comment="Request timeout in seconds",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        comment="Extraction provider configurations for entity extraction",
    )

    # Unique constraint on provider name within tenant
    op.create_unique_constraint(
        "uq_extraction_providers_tenant_name",
        "extraction_providers",
        ["tenant_id", "name"],
    )

    # Index on provider type for filtering
    op.create_index(
        "ix_extraction_providers_type",
        "extraction_providers",
        ["provider_type"],
    )

    # ==========================================================================
    # Enable Row Level Security
    # ==========================================================================

    op.execute("ALTER TABLE extraction_providers ENABLE ROW LEVEL SECURITY;")

    # ==========================================================================
    # Create RLS Policies
    # ==========================================================================

    # Policy pattern uses COALESCE/NULLIF for robustness
    # This handles cases where the session variable may be empty string

    op.execute(
        """
        CREATE POLICY extraction_providers_tenant_isolation
        ON extraction_providers
        FOR ALL
        USING (
            tenant_id = COALESCE(
                NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
                '00000000-0000-0000-0000-000000000000'::UUID
            )
        )
        WITH CHECK (
            tenant_id = COALESCE(
                NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
                '00000000-0000-0000-0000-000000000000'::UUID
            )
        );
    """
    )

    # ==========================================================================
    # Grant Permissions
    # ==========================================================================

    # App user (RLS enforced)
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON extraction_providers
        TO knowledge_mapper_app_user;
    """
    )

    # Migration user (bypass RLS for maintenance)
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON extraction_providers
        TO knowledge_mapper_migration_user;
    """
    )


def downgrade() -> None:
    """Remove extraction_providers table and RLS policies."""

    # Drop policies
    op.execute(
        "DROP POLICY IF EXISTS extraction_providers_tenant_isolation ON extraction_providers"
    )

    # Drop table
    op.drop_table("extraction_providers")

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS extraction_provider_type")

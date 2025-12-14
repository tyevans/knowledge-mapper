"""Add inference tables with RLS.

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2025-12-14

This migration creates:
- inference_providers: Provider configuration storage
- inference_requests: History projection table
- RLS policies for multi-tenant isolation
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


# revision identifiers, used by Alembic.
revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create inference tables and RLS policies."""

    # ==========================================================================
    # Create Enum Types
    # ==========================================================================

    op.execute(
        """
        CREATE TYPE inference_provider_type AS ENUM (
            'ollama',
            'openai',
            'anthropic',
            'groq'
        );
    """
    )

    op.execute(
        """
        CREATE TYPE inference_status AS ENUM (
            'pending',
            'in_progress',
            'completed',
            'failed',
            'cancelled'
        );
    """
    )

    # ==========================================================================
    # Create inference_providers Table
    # ==========================================================================

    op.create_table(
        "inference_providers",
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
            sa.Enum(
                "ollama",
                "openai",
                "anthropic",
                "groq",
                name="inference_provider_type",
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
        sa.Column("default_model", sa.String(255), nullable=True),
        sa.Column(
            "default_temperature",
            sa.Float(),
            nullable=False,
            server_default="0.7",
        ),
        sa.Column(
            "default_max_tokens",
            sa.Integer(),
            nullable=False,
            server_default="1024",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "rate_limit_preset",
            sa.String(50),
            nullable=True,
            server_default="'balanced'",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        comment="Provider configurations for inference testing",
    )

    # Unique constraint on provider name within tenant
    op.create_unique_constraint(
        "uq_inference_providers_tenant_name",
        "inference_providers",
        ["tenant_id", "name"],
    )

    # ==========================================================================
    # Create inference_requests Table
    # ==========================================================================

    op.create_table(
        "inference_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "provider_id",
            UUID(as_uuid=True),
            sa.ForeignKey("inference_providers.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            nullable=True,
            index=True,
            comment="User who made the request",
        ),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "in_progress",
                "completed",
                "failed",
                "cancelled",
                name="inference_status",
                create_type=False,
            ),
            nullable=False,
            server_default="'pending'",
        ),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "duration_ms",
            sa.Integer(),
            nullable=True,
            comment="Request duration in milliseconds",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "parameters",
            JSON(),
            nullable=False,
            server_default="{}",
            comment="Request parameters (temperature, max_tokens, etc.)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        comment="Inference request history (projection from events)",
    )

    # Additional indexes for common queries
    op.create_index(
        "ix_inference_requests_tenant_created",
        "inference_requests",
        ["tenant_id", "created_at"],
    )

    op.create_index(
        "ix_inference_requests_tenant_status",
        "inference_requests",
        ["tenant_id", "status"],
    )

    # ==========================================================================
    # Enable Row Level Security
    # ==========================================================================

    op.execute("ALTER TABLE inference_providers ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE inference_requests ENABLE ROW LEVEL SECURITY;")

    # ==========================================================================
    # Create RLS Policies
    # ==========================================================================

    # Policy pattern uses COALESCE/NULLIF for robustness
    # This handles cases where the session variable may be empty string

    # inference_providers policies
    op.execute(
        """
        CREATE POLICY inference_providers_tenant_isolation
        ON inference_providers
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

    # inference_requests policies
    op.execute(
        """
        CREATE POLICY inference_requests_tenant_isolation
        ON inference_requests
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
        GRANT SELECT, INSERT, UPDATE, DELETE ON inference_providers
        TO knowledge_mapper_app_user;
    """
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON inference_requests
        TO knowledge_mapper_app_user;
    """
    )

    # Migration user (bypass RLS for maintenance)
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON inference_providers
        TO knowledge_mapper_migration_user;
    """
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON inference_requests
        TO knowledge_mapper_migration_user;
    """
    )


def downgrade() -> None:
    """Remove inference tables and RLS policies."""

    # Drop policies
    op.execute(
        "DROP POLICY IF EXISTS inference_requests_tenant_isolation ON inference_requests"
    )
    op.execute(
        "DROP POLICY IF EXISTS inference_providers_tenant_isolation ON inference_providers"
    )

    # Drop tables
    op.drop_table("inference_requests")
    op.drop_table("inference_providers")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS inference_status")
    op.execute("DROP TYPE IF EXISTS inference_provider_type")

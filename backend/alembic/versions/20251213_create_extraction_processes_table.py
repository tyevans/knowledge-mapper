"""Create extraction_processes table for tracking extraction status.

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2025-12-13

Creates the extraction_processes table as a projection/read model for
tracking the status of entity extraction for each scraped page.
RLS enabled for tenant isolation.

Note: event_outbox table already exists from 20251212_2300_add_event_sourcing_tables.py
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f6g7h8i9j0k1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create extraction_processes table with RLS."""

    # =========================================================================
    # extraction_processes table
    # =========================================================================
    op.create_table(
        "extraction_processes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("scraped_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="pending",
            comment="Status: pending, processing, completed, failed, retrying",
        ),
        sa.Column("page_url", sa.Text, nullable=True, comment="URL of the page being processed"),
        sa.Column("content_hash", sa.String(64), nullable=True, comment="SHA-256 hash of page content"),
        sa.Column(
            "entity_count",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Number of entities extracted",
        ),
        sa.Column(
            "relationship_count",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Number of relationships extracted",
        ),
        sa.Column(
            "retry_count",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Number of retry attempts",
        ),
        sa.Column("last_error", sa.Text, nullable=True, comment="Last error message"),
        sa.Column("last_error_type", sa.String(100), nullable=True, comment="Last error type/class"),
        sa.Column(
            "extraction_method",
            sa.String(50),
            nullable=True,
            comment="Method used: llm_claude, llm_ollama, schema_org, etc.",
        ),
        sa.Column(
            "extraction_config",
            JSONB,
            nullable=False,
            server_default="{}",
            comment="Configuration used for extraction",
        ),
        sa.Column("worker_id", sa.String(100), nullable=True, comment="ID of worker processing this"),
        sa.Column("duration_ms", sa.Integer, nullable=True, comment="Processing duration in milliseconds"),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When extraction was requested",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When extraction processing started",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When extraction completed successfully",
        ),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When extraction last failed",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        comment="Tracks extraction process status for each scraped page",
    )

    # =========================================================================
    # Indexes for common queries
    # =========================================================================
    op.create_index(
        "ix_extraction_processes_tenant_status",
        "extraction_processes",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_extraction_processes_page_id",
        "extraction_processes",
        ["page_id"],
        unique=True,  # One extraction process per page
    )

    # =========================================================================
    # Enable Row-Level Security (RLS)
    # =========================================================================
    op.execute("ALTER TABLE extraction_processes ENABLE ROW LEVEL SECURITY")

    # Create RLS policy using same pattern as other scraping tables
    # Uses COALESCE with current_setting to handle cases where tenant context is not set
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON extraction_processes
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
    """Drop extraction_processes table."""

    # Drop RLS policy first
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON extraction_processes")
    op.execute("ALTER TABLE extraction_processes DISABLE ROW LEVEL SECURITY")

    # Drop table (indexes are dropped automatically)
    op.drop_table("extraction_processes")
